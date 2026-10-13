"""
ACE PO3 engine (Python reference version)
=========================================

This file is the "brain" of the project. It reads bars one at a time and
decides when to BUY or SELL using your ICT notes:

    1. ACCUMULATION  overnight range builds liquidity           (PO3 phase 1)
    2. MANIPULATION  price sweeps a high or a low               (PO3 phase 2)
    3. CISD / MSS    a candle closes through the last opposing run (MMXM)
    4. PD ARRAY      price retests an FVG / iFVG / order block -> ENTRY
    5. DISTRIBUTION  targets come from STDV of the manipulation leg
                     (-2 = TP1 retrace zone, -4 = TP2 reversal zone)

The C++ engine in cpp/src/engine.cpp is a line-by-line translation of this
file. If you change the logic here, change it there too, then run
`python python/compare_engines.py` to prove they still agree.

A note on "na": like Pine Script, we use NaN (not-a-number) for "no value
yet". Any comparison with NaN is False, which is exactly how Pine behaves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

NAN = math.nan


# ─────────────────────────────── settings ───────────────────────────────
@dataclass
class Config:
    # Sessions, in minutes after midnight New York time (9:30 = 570).
    trade_start: int = 9 * 60 + 30      # kill zone start
    trade_end: int = 11 * 60 + 30       # kill zone end
    acc_start: int = 18 * 60            # accumulation (overnight) range start
    acc_end: int = 9 * 60 + 30          # accumulation range end
    flat_start: int = 15 * 60 + 55      # force-flat window (Apex: flat before 16:59)
    flat_end: int = 18 * 60

    # Manipulation = which liquidity sweeps arm a setup
    use_acc: bool = True                # accumulation range high/low
    use_pd: bool = True                 # previous day high/low
    use_piv: bool = True                # most recent swing high/low
    piv_len: int = 5                    # swing strength (bars on each side)
    leg_look: int = 20                  # bars to look back for the start of the manipulation leg
    max_wait: int = 30                  # setup expires after this many bars

    # PD array entries
    use_fvg: bool = True
    use_ifvg: bool = True
    use_ob: bool = True
    req_cisd: bool = True               # require CISD before any entry
    min_gap_ticks: int = 2
    tick: float = 0.25                  # NQ / MNQ tick size

    # Standard deviations (targets)
    sd_wick_to_body: bool = False       # False = wick to wick
    tp1_dev: float = -2.0
    tp2_dev: float = -4.0
    tp1_frac: float = 0.5               # fraction closed at TP1
    move_be: bool = True

    # Risk
    sl_buf_ticks: int = 4
    min_rr: float = 1.5
    max_stop_pts: float = 0.0           # 0 = off
    max_trades: int = 2

    # Bias (OHLC / OLHC of the 4H candle)
    use_bias: bool = True
    bias_thr_atr: float = 0.5
    atr_len: int = 14


# ─────────────────────────────── data types ───────────────────────────────
@dataclass
class Bar:
    ts: int            # unix seconds (UTC)
    session_date: int  # CME trading day as YYYYMMDD (starts 18:00 ET the evening before)
    minute: int        # minutes after midnight, New York time
    open: float
    high: float
    low: float
    close: float


@dataclass
class Zone:
    top: float
    bot: float
    bar: int
    kind: str          # "FVG", "iFVG" or "OB"


@dataclass
class Setup:
    """State for one side (short or long) of the PO3 model."""
    armed: bool = False
    bar: int = 0
    ext: float = NAN       # STDV "1": manipulation extreme
    start: float = NAN     # STDV "0": start of manipulation leg
    cisd: bool = False
    zones: list = field(default_factory=list)


@dataclass
class Event:
    kind: str          # "SWEEP", "SIGNAL", "EXIT", "MMXM"
    bar: int
    ts: int
    direction: int     # +1 long / -1 short
    price: float
    stop: float = NAN
    tp1: float = NAN
    tp2: float = NAN
    setup: str = ""
    r: float = NAN     # realised R (EXIT only)


def in_window(minute: int, start: int, end: int) -> bool:
    """True if `minute` is inside [start, end). Handles windows that cross midnight."""
    if start <= end:
        return start <= minute < end
    return minute >= start or minute < end


# ─────────────────────────────── the engine ───────────────────────────────
class Engine:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        c = self.cfg
        # bar history
        self.o: list[float] = []
        self.h: list[float] = []
        self.l: list[float] = []
        self.c: list[float] = []
        self.prev_bar: Bar | None = None
        self.prev_in_acc = False

        # ATR (Wilder / RMA, same as Pine ta.atr)
        self.atr = NAN
        self._tr_seed: list[float] = []

        # liquidity levels
        self.acc_hi = NAN; self.acc_lo = NAN
        self.acc_hi_taken = False; self.acc_lo_taken = False
        self.sess_hi = NAN; self.sess_lo = NAN
        self.pdh = NAN; self.pdl = NAN
        self.pdh_taken = False; self.pdl_taken = False
        self.sw_hi = NAN; self.sw_lo = NAN
        self.sw_hi_taken = False; self.sw_lo_taken = False

        # 4H bias candle
        self.htf_key = -1
        self.h_o = NAN; self.h_h = NAN; self.h_l = NAN
        self.bias = 0

        # FVG history (for inversions)
        self.bull_fvgs: list[Zone] = []
        self.bear_fvgs: list[Zone] = []

        # candle runs (for CISD / order blocks)
        self.up_run_open = NAN; self.up_run_high = NAN
        self.dn_run_open = NAN; self.dn_run_low = NAN

        # setups
        self.short = Setup()
        self.long = Setup()

        # simulated position
        self.pos = 0
        self.pos_bar = 0
        self.entry = NAN; self.stop = NAN; self.t1 = NAN; self.t2 = NAN
        self.risk = NAN; self.t1_hit = False; self.trade_r = 0.0
        self.trades_today = 0

        # MMXM tracker
        self.mm_dir = 0
        self.mm4 = NAN

        self.events: list[Event] = []

    # ─────────────── helpers ───────────────
    def _update_atr(self, i: int) -> None:
        h, l = self.h[i], self.l[i]
        tr = h - l if i == 0 else max(h - l, abs(h - self.c[i - 1]), abs(l - self.c[i - 1]))
        n = self.cfg.atr_len
        if math.isnan(self.atr):
            self._tr_seed.append(tr)
            if len(self._tr_seed) == n:
                self.atr = sum(self._tr_seed) / n
        else:
            self.atr = (self.atr * (n - 1) + tr) / n

    def _pivots(self, i: int) -> tuple[float, float]:
        """Confirmed swing high/low at bar i - piv_len (like ta.pivothigh)."""
        L = self.cfg.piv_len
        if i < 2 * L:
            return NAN, NAN
        cidx = i - L
        ch, cl = self.h[cidx], self.l[cidx]
        ph = ch if (all(ch > self.h[j] for j in range(cidx - L, cidx))
                    and all(ch >= self.h[j] for j in range(cidx + 1, i + 1))) else NAN
        pl = cl if (all(cl < self.l[j] for j in range(cidx - L, cidx))
                    and all(cl <= self.l[j] for j in range(cidx + 1, i + 1))) else NAN
        return ph, pl

    def _emit(self, ev: Event) -> None:
        self.events.append(ev)

    # ─────────────── main step: call once per bar ───────────────
    def on_bar(self, b: Bar) -> list[Event]:
        cfg = self.cfg
        out_start = len(self.events)
        self.o.append(b.open); self.h.append(b.high); self.l.append(b.low); self.c.append(b.close)
        i = len(self.c) - 1
        o, h, l, c = b.open, b.high, b.low, b.close
        tick = cfg.tick

        in_trade = in_window(b.minute, cfg.trade_start, cfg.trade_end)
        in_acc = in_window(b.minute, cfg.acc_start, cfg.acc_end)
        in_flat = in_window(b.minute, cfg.flat_start, cfg.flat_end)
        new_day = self.prev_bar is None or b.session_date != self.prev_bar.session_date

        self._update_atr(i)
        lo_win = range(max(0, i - cfg.leg_look + 1), i + 1)
        leg_lo = min(self.l[j] for j in lo_win)
        leg_lo_body = min(min(self.o[j], self.c[j]) for j in lo_win)
        leg_hi = max(self.h[j] for j in lo_win)
        leg_hi_body = max(max(self.o[j], self.c[j]) for j in lo_win)

        # ── 1. accumulation range ──
        if in_acc and not self.prev_in_acc:
            self.acc_hi, self.acc_lo = h, l
            self.acc_hi_taken = self.acc_lo_taken = False
        elif in_acc:
            self.acc_hi = max(self.acc_hi, h)
            self.acc_lo = min(self.acc_lo, l)
        acc_done = (not in_acc) and not math.isnan(self.acc_hi)

        # previous day high / low
        if new_day:
            self.pdh, self.pdl = self.sess_hi, self.sess_lo
            self.sess_hi, self.sess_lo = h, l
            self.pdh_taken = self.pdl_taken = False
        else:
            self.sess_hi = max(self.sess_hi, h)
            self.sess_lo = min(self.sess_lo, l)

        # swing highs / lows
        ph, pl = self._pivots(i)
        if not math.isnan(ph):
            self.sw_hi, self.sw_hi_taken = ph, False
        if not math.isnan(pl):
            self.sw_lo, self.sw_lo_taken = pl, False

        # ── 2. manipulation: liquidity sweeps ──
        bsl = ssl = False
        if cfg.use_acc and acc_done and not self.acc_hi_taken and h > self.acc_hi:
            self.acc_hi_taken = bsl = True
        if cfg.use_acc and acc_done and not self.acc_lo_taken and l < self.acc_lo:
            self.acc_lo_taken = ssl = True
        if cfg.use_pd and not self.pdh_taken and h > self.pdh:
            self.pdh_taken = bsl = True
        if cfg.use_pd and not self.pdl_taken and l < self.pdl:
            self.pdl_taken = ssl = True
        if cfg.use_piv and not self.sw_hi_taken and h > self.sw_hi:
            self.sw_hi_taken = bsl = True
        if cfg.use_piv and not self.sw_lo_taken and l < self.sw_lo:
            self.sw_lo_taken = ssl = True
        if bsl:
            self._emit(Event("SWEEP", i, b.ts, -1, h, setup="BSL"))
        if ssl:
            self._emit(Event("SWEEP", i, b.ts, 1, l, setup="SSL"))

        # ── bias: OHLC / OLHC of the 4H candle (CME 4H opens 18,22,2,6,10,14 ET) ──
        key = b.session_date * 10 + ((b.minute - 18 * 60) % 1440) // 240
        if key != self.htf_key:
            self.htf_key = key
            self.h_o, self.h_h, self.h_l = o, h, l
        else:
            self.h_h = max(self.h_h, h)
            self.h_l = min(self.h_l, l)
        thr = self.atr * cfg.bias_thr_atr
        up_m = self.h_h - self.h_o >= thr
        dn_m = self.h_o - self.h_l >= thr
        bias = 0
        if up_m and not dn_m:
            bias = -1                      # manipulated up first -> expect OHLC (bearish)
        elif dn_m and not up_m:
            bias = 1                       # manipulated down first -> expect OLHC (bullish)
        elif up_m and dn_m:
            bias = -1 if c < self.h_o else 1
        self.bias = bias
        short_ok = (not cfg.use_bias) or bias == -1
        long_ok = (not cfg.use_bias) or bias == 1

        # fair value gaps on this bar
        gap_min = cfg.min_gap_ticks * tick
        bull_fvg = i >= 2 and l > self.h[i - 2] and (l - self.h[i - 2]) >= gap_min
        bear_fvg = i >= 2 and h < self.l[i - 2] and (self.l[i - 2] - h) >= gap_min

        # ── simulated position: check exits ──
        if self.pos != 0 and i > self.pos_bar:
            self._manage_position(b, i, in_flat)

        if new_day:
            self.trades_today = 0
        flat = self.pos == 0

        # ── arm / extend setups ──
        s, lg = self.short, self.long
        s_fresh = (bsl and not s.armed) or (s.armed and s.cisd and h > s.ext)
        s_extend = (not s_fresh) and s.armed and h > s.ext
        if s_fresh:
            s.armed, s.bar, s.ext = True, i, h
            s.start = leg_lo_body if cfg.sd_wick_to_body else leg_lo
            s.cisd = False
            s.zones.clear()
            lg.armed = False               # BSL reached = long's draw on liquidity delivered
        elif s_extend:
            s.ext, s.bar = h, i

        l_fresh = (ssl and not lg.armed) or (lg.armed and lg.cisd and l < lg.ext)
        l_extend = (not l_fresh) and lg.armed and l < lg.ext
        if l_fresh:
            lg.armed, lg.bar, lg.ext = True, i, l
            lg.start = leg_hi_body if cfg.sd_wick_to_body else leg_hi
            lg.cisd = False
            lg.zones.clear()
            if not s_fresh:
                s.armed = False
        elif l_extend:
            lg.ext, lg.bar = l, i

        if s.armed and i - s.bar > cfg.max_wait:
            s.armed = False
        if lg.armed and i - lg.bar > cfg.max_wait:
            lg.armed = False

        # ── 3. CISD + order blocks ──
        if s.armed and not s.cisd and c < self.up_run_open:
            s.cisd = True
            if cfg.use_ob:
                s.zones.append(Zone(self.up_run_high, self.up_run_open, i, "OB"))
        if lg.armed and not lg.cisd and c > self.dn_run_open:
            lg.cisd = True
            if cfg.use_ob:
                lg.zones.append(Zone(self.dn_run_open, self.dn_run_low, i, "OB"))

        # update candle runs (after the CISD check)
        prev_up = i > 0 and self.c[i - 1] > self.o[i - 1]
        prev_dn = i > 0 and self.c[i - 1] < self.o[i - 1]
        if c > o:
            if not prev_up:
                self.up_run_open, self.up_run_high = o, h
            else:
                self.up_run_high = max(self.up_run_high, h)
        if c < o:
            if not prev_dn:
                self.dn_run_open, self.dn_run_low = o, l
            else:
                self.dn_run_low = min(self.dn_run_low, l)

        # ── 4. PD arrays: new FVGs + inversions ──
        if bear_fvg and s.armed and cfg.use_fvg:
            s.zones.append(Zone(self.l[i - 2], h, i, "FVG"))
        if bull_fvg and lg.armed and cfg.use_fvg:
            lg.zones.append(Zone(l, self.h[i - 2], i, "FVG"))

        for z in list(reversed(self.bull_fvgs)):          # bullish FVG closed through -> bearish iFVG
            if c < z.bot:
                if s.armed and cfg.use_ifvg and z.bar >= s.bar - cfg.leg_look:
                    s.zones.append(Zone(z.top, z.bot, i, "iFVG"))
                self.bull_fvgs.remove(z)
        for z in list(reversed(self.bear_fvgs)):          # bearish FVG closed through -> bullish iFVG
            if c > z.top:
                if lg.armed and cfg.use_ifvg and z.bar >= lg.bar - cfg.leg_look:
                    lg.zones.append(Zone(z.top, z.bot, i, "iFVG"))
                self.bear_fvgs.remove(z)

        if bull_fvg:
            self.bull_fvgs.append(Zone(l, self.h[i - 2], i, "FVG"))
            if len(self.bull_fvgs) > 30:
                self.bull_fvgs.pop(0)
        if bear_fvg:
            self.bear_fvgs.append(Zone(self.l[i - 2], h, i, "FVG"))
            if len(self.bear_fvgs) > 30:
                self.bear_fvgs.pop(0)

        # ── 5. entries ──
        can_short = s.armed and (s.cisd or not cfg.req_cisd) and in_trade and flat \
            and short_ok and self.trades_today < cfg.max_trades
        can_long = lg.armed and (lg.cisd or not cfg.req_cisd) and in_trade and flat \
            and long_ok and self.trades_today < cfg.max_trades

        signal: Event | None = None

        hit: Zone | None = None
        if s.armed:
            for z in list(reversed(s.zones)):
                if c > z.top:
                    s.zones.remove(z)                    # zone failed
                elif hit is None and can_short and z.bar < i and h >= z.bot and c < o:
                    hit = z
        if hit is not None:
            one, zero = s.ext, s.start
            L = one - zero
            stp = one + cfg.sl_buf_ticks * tick
            t1 = zero + cfg.tp1_dev * L
            t2 = zero + cfg.tp2_dev * L
            risk = stp - c
            rr = (c - t1) / risk if risk > 0 else 0.0
            if L > 0 and risk > 0 and rr >= cfg.min_rr and (cfg.max_stop_pts == 0 or risk <= cfg.max_stop_pts):
                signal = Event("SIGNAL", i, b.ts, -1, c, stp, t1, t2, hit.kind)
                s.armed = False
                self.mm_dir, self.mm4 = -1, zero + (-4.0) * L

        hit = None
        if lg.armed:
            for z in list(reversed(lg.zones)):
                if c < z.bot:
                    lg.zones.remove(z)
                elif hit is None and signal is None and can_long and z.bar < i and l <= z.top and c > o:
                    hit = z
        if hit is not None:
            one, zero = lg.ext, lg.start
            L = one - zero                               # negative for longs -> targets project up
            stp = one - cfg.sl_buf_ticks * tick
            t1 = zero + cfg.tp1_dev * L
            t2 = zero + cfg.tp2_dev * L
            risk = c - stp
            rr = (t1 - c) / risk if risk > 0 else 0.0
            if L < 0 and risk > 0 and rr >= cfg.min_rr and (cfg.max_stop_pts == 0 or risk <= cfg.max_stop_pts):
                signal = Event("SIGNAL", i, b.ts, 1, c, stp, t1, t2, hit.kind)
                lg.armed = False
                self.mm_dir, self.mm4 = 1, zero + (-4.0) * L

        if signal is not None:
            self._emit(signal)
            self.pos, self.pos_bar = signal.direction, i
            self.entry, self.stop, self.t1, self.t2 = c, signal.stop, signal.tp1, signal.tp2
            self.risk = abs(c - signal.stop)
            self.t1_hit, self.trade_r = False, 0.0
            self.trades_today += 1

        # ── MMXM switch at -4 STDV ──
        if self.mm_dir == -1 and l <= self.mm4:
            self._emit(Event("MMXM", i, b.ts, 1, l, setup="MMSM->MMBM"))
            self.mm_dir = 0
        if self.mm_dir == 1 and h >= self.mm4:
            self._emit(Event("MMXM", i, b.ts, -1, h, setup="MMBM->MMSM"))
            self.mm_dir = 0

        self.prev_bar = b
        self.prev_in_acc = in_acc
        return self.events[out_start:]

    # ─────────────── position management (stop / TP1 / TP2 / flatten) ───────────────
    def _manage_position(self, b: Bar, i: int, in_flat: bool) -> None:
        cfg = self.cfg
        d = self.pos
        exit_px = NAN
        why = ""
        if in_flat:
            exit_px, why = b.close, "Flat"
        else:
            stop_hit = b.low <= self.stop if d == 1 else b.high >= self.stop
            if stop_hit:
                exit_px, why = self.stop, ("BE" if self.t1_hit else "SL")
            else:
                t1_reached = b.high >= self.t1 if d == 1 else b.low <= self.t1
                if not self.t1_hit and t1_reached:
                    self.t1_hit = True
                    self.trade_r += cfg.tp1_frac * d * (self.t1 - self.entry) / self.risk
                    if cfg.tp1_frac >= 1:
                        exit_px, why = self.t1, "TP1"
                    elif cfg.move_be:
                        self.stop = self.entry
                t2_reached = b.high >= self.t2 if d == 1 else b.low <= self.t2
                if math.isnan(exit_px) and t2_reached:
                    exit_px, why = self.t2, "TP2"
        if not math.isnan(exit_px):
            rem = (1 - cfg.tp1_frac) if self.t1_hit else 1.0
            self.trade_r += rem * d * (exit_px - self.entry) / self.risk
            self._emit(Event("EXIT", i, b.ts, d, exit_px, setup=why, r=self.trade_r))
            self.pos = 0


def run(bars, cfg: Config | None = None) -> list[Event]:
    """Convenience: feed a list of Bar objects through a fresh engine."""
    eng = Engine(cfg)
    for b in bars:
        eng.on_bar(b)
    return eng.events
