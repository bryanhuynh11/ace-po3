// ACE PO3 engine: C++ implementation. Mirrors python/po3/engine.py step by step.
#include "po3/engine.hpp"

#include <algorithm>
#include <cmath>

namespace po3 {

bool in_window(int minute, int start, int end) {
    if (start <= end) return start <= minute && minute < end;
    return minute >= start || minute < end;     // window crosses midnight
}

Engine::Engine(Config cfg) : cfg_(cfg) {}

void Engine::update_atr(int i) {
    const double h = h_[i], l = l_[i];
    double tr = h - l;
    if (i > 0) tr = std::max({h - l, std::abs(h - c_[i - 1]), std::abs(l - c_[i - 1])});
    const int n = cfg_.atr_len;
    if (std::isnan(atr_)) {
        tr_seed_.push_back(tr);
        if (static_cast<int>(tr_seed_.size()) == n) {
            double sum = 0.0;
            for (double x : tr_seed_) sum += x;
            atr_ = sum / n;
        }
    } else {
        atr_ = (atr_ * (n - 1) + tr) / n;
    }
}

void Engine::pivots(int i, double& ph, double& pl) const {
    ph = NaN;
    pl = NaN;
    const int L = cfg_.piv_len;
    if (i < 2 * L) return;
    const int cidx = i - L;
    const double ch = h_[cidx], cl = l_[cidx];
    bool is_h = true, is_l = true;
    for (int j = cidx - L; j < cidx; ++j) {
        if (!(ch > h_[j])) is_h = false;
        if (!(cl < l_[j])) is_l = false;
    }
    for (int j = cidx + 1; j <= i; ++j) {
        if (!(ch >= h_[j])) is_h = false;
        if (!(cl <= l_[j])) is_l = false;
    }
    if (is_h) ph = ch;
    if (is_l) pl = cl;
}

std::vector<Event> Engine::on_bar(const Bar& b) {
    const size_t out_start = events_.size();
    o_.push_back(b.open);
    h_.push_back(b.high);
    l_.push_back(b.low);
    c_.push_back(b.close);
    const int i = static_cast<int>(c_.size()) - 1;
    const double o = b.open, h = b.high, l = b.low, c = b.close;
    const double tick = cfg_.tick;

    const bool in_trade = in_window(b.minute, cfg_.trade_start, cfg_.trade_end);
    const bool in_acc = in_window(b.minute, cfg_.acc_start, cfg_.acc_end);
    const bool in_flat = in_window(b.minute, cfg_.flat_start, cfg_.flat_end);
    const bool new_day = !has_prev_ || b.session_date != prev_session_;

    update_atr(i);
    double leg_lo = l_[std::max(0, i - cfg_.leg_look + 1)];
    double leg_hi = h_[std::max(0, i - cfg_.leg_look + 1)];
    double leg_lo_body = std::min(o_[std::max(0, i - cfg_.leg_look + 1)], c_[std::max(0, i - cfg_.leg_look + 1)]);
    double leg_hi_body = std::max(o_[std::max(0, i - cfg_.leg_look + 1)], c_[std::max(0, i - cfg_.leg_look + 1)]);
    for (int j = std::max(0, i - cfg_.leg_look + 1); j <= i; ++j) {
        leg_lo = std::min(leg_lo, l_[j]);
        leg_hi = std::max(leg_hi, h_[j]);
        leg_lo_body = std::min(leg_lo_body, std::min(o_[j], c_[j]));
        leg_hi_body = std::max(leg_hi_body, std::max(o_[j], c_[j]));
    }

    // ── 1. accumulation range ──
    if (in_acc && !prev_in_acc_) {
        acc_hi_ = h;
        acc_lo_ = l;
        acc_hi_taken_ = acc_lo_taken_ = false;
    } else if (in_acc) {
        acc_hi_ = std::max(acc_hi_, h);
        acc_lo_ = std::min(acc_lo_, l);
    }
    const bool acc_done = !in_acc && !std::isnan(acc_hi_);

    // previous day high / low
    if (new_day) {
        pdh_ = sess_hi_;
        pdl_ = sess_lo_;
        sess_hi_ = h;
        sess_lo_ = l;
        pdh_taken_ = pdl_taken_ = false;
    } else {
        sess_hi_ = std::max(sess_hi_, h);
        sess_lo_ = std::min(sess_lo_, l);
    }

    // swing highs / lows
    double ph, pl;
    pivots(i, ph, pl);
    if (!std::isnan(ph)) { sw_hi_ = ph; sw_hi_taken_ = false; }
    if (!std::isnan(pl)) { sw_lo_ = pl; sw_lo_taken_ = false; }

    // ── 2. manipulation: liquidity sweeps ──
    bool bsl = false, ssl = false;
    if (cfg_.use_acc && acc_done && !acc_hi_taken_ && h > acc_hi_) { acc_hi_taken_ = true; bsl = true; }
    if (cfg_.use_acc && acc_done && !acc_lo_taken_ && l < acc_lo_) { acc_lo_taken_ = true; ssl = true; }
    if (cfg_.use_pd && !pdh_taken_ && h > pdh_) { pdh_taken_ = true; bsl = true; }
    if (cfg_.use_pd && !pdl_taken_ && l < pdl_) { pdl_taken_ = true; ssl = true; }
    if (cfg_.use_piv && !sw_hi_taken_ && h > sw_hi_) { sw_hi_taken_ = true; bsl = true; }
    if (cfg_.use_piv && !sw_lo_taken_ && l < sw_lo_) { sw_lo_taken_ = true; ssl = true; }
    if (bsl) events_.push_back({"SWEEP", i, b.ts, -1, h, NaN, NaN, NaN, "BSL", NaN});
    if (ssl) events_.push_back({"SWEEP", i, b.ts, 1, l, NaN, NaN, NaN, "SSL", NaN});

    // ── bias: OHLC / OLHC of the 4H candle ──
    const int bucket = (((b.minute - 18 * 60) % 1440) + 1440) % 1440 / 240;
    const long long key = static_cast<long long>(b.session_date) * 10 + bucket;
    if (key != htf_key_) {
        htf_key_ = key;
        h_o_ = o;
        h_h_ = h;
        h_l_ = l;
    } else {
        h_h_ = std::max(h_h_, h);
        h_l_ = std::min(h_l_, l);
    }
    const double thr = atr_ * cfg_.bias_thr_atr;
    const bool up_m = h_h_ - h_o_ >= thr;
    const bool dn_m = h_o_ - h_l_ >= thr;
    int bias = 0;
    if (up_m && !dn_m) bias = -1;
    else if (dn_m && !up_m) bias = 1;
    else if (up_m && dn_m) bias = c < h_o_ ? -1 : 1;
    bias_ = bias;
    const bool short_ok = !cfg_.use_bias || bias == -1;
    const bool long_ok = !cfg_.use_bias || bias == 1;

    // fair value gaps on this bar
    const double gap_min = cfg_.min_gap_ticks * tick;
    const bool bull_fvg = i >= 2 && l > h_[i - 2] && (l - h_[i - 2]) >= gap_min;
    const bool bear_fvg = i >= 2 && h < l_[i - 2] && (l_[i - 2] - h) >= gap_min;

    // ── simulated position exits ──
    if (pos_ != 0 && i > pos_bar_) manage_position(b, i, in_flat);

    if (new_day) trades_today_ = 0;
    const bool flat = pos_ == 0;

    // ── arm / extend setups ──
    Setup& s = short_;
    Setup& lg = long_;
    const bool s_fresh = (bsl && !s.armed) || (s.armed && s.cisd && h > s.ext);
    const bool s_extend = !s_fresh && s.armed && h > s.ext;
    if (s_fresh) {
        s.armed = true; s.bar = i; s.ext = h;
        s.start = cfg_.sd_wick_to_body ? leg_lo_body : leg_lo;
        s.cisd = false;
        s.zones.clear();
        lg.armed = false;
    } else if (s_extend) {
        s.ext = h; s.bar = i;
    }

    const bool l_fresh = (ssl && !lg.armed) || (lg.armed && lg.cisd && l < lg.ext);
    const bool l_extend = !l_fresh && lg.armed && l < lg.ext;
    if (l_fresh) {
        lg.armed = true; lg.bar = i; lg.ext = l;
        lg.start = cfg_.sd_wick_to_body ? leg_hi_body : leg_hi;
        lg.cisd = false;
        lg.zones.clear();
        if (!s_fresh) s.armed = false;
    } else if (l_extend) {
        lg.ext = l; lg.bar = i;
    }

    if (s.armed && i - s.bar > cfg_.max_wait) s.armed = false;
    if (lg.armed && i - lg.bar > cfg_.max_wait) lg.armed = false;

    // ── 3. CISD + order blocks ──
    if (s.armed && !s.cisd && c < up_run_open_) {
        s.cisd = true;
        if (cfg_.use_ob) s.zones.push_back({up_run_high_, up_run_open_, i, "OB"});
    }
    if (lg.armed && !lg.cisd && c > dn_run_open_) {
        lg.cisd = true;
        if (cfg_.use_ob) lg.zones.push_back({dn_run_open_, dn_run_low_, i, "OB"});
    }

    const bool prev_up = i > 0 && c_[i - 1] > o_[i - 1];
    const bool prev_dn = i > 0 && c_[i - 1] < o_[i - 1];
    if (c > o) {
        if (!prev_up) { up_run_open_ = o; up_run_high_ = h; }
        else up_run_high_ = std::max(up_run_high_, h);
    }
    if (c < o) {
        if (!prev_dn) { dn_run_open_ = o; dn_run_low_ = l; }
        else dn_run_low_ = std::min(dn_run_low_, l);
    }

    // ── 4. PD arrays ──
    if (bear_fvg && s.armed && cfg_.use_fvg) s.zones.push_back({l_[i - 2], h, i, "FVG"});
    if (bull_fvg && lg.armed && cfg_.use_fvg) lg.zones.push_back({l, h_[i - 2], i, "FVG"});

    for (int k = static_cast<int>(bull_fvgs_.size()) - 1; k >= 0; --k) {
        const Zone z = bull_fvgs_[k];
        if (c < z.bot) {
            if (s.armed && cfg_.use_ifvg && z.bar >= s.bar - cfg_.leg_look)
                s.zones.push_back({z.top, z.bot, i, "iFVG"});
            bull_fvgs_.erase(bull_fvgs_.begin() + k);
        }
    }
    for (int k = static_cast<int>(bear_fvgs_.size()) - 1; k >= 0; --k) {
        const Zone z = bear_fvgs_[k];
        if (c > z.top) {
            if (lg.armed && cfg_.use_ifvg && z.bar >= lg.bar - cfg_.leg_look)
                lg.zones.push_back({z.top, z.bot, i, "iFVG"});
            bear_fvgs_.erase(bear_fvgs_.begin() + k);
        }
    }
    if (bull_fvg) {
        bull_fvgs_.push_back({l, h_[i - 2], i, "FVG"});
        if (bull_fvgs_.size() > 30) bull_fvgs_.erase(bull_fvgs_.begin());
    }
    if (bear_fvg) {
        bear_fvgs_.push_back({l_[i - 2], h, i, "FVG"});
        if (bear_fvgs_.size() > 30) bear_fvgs_.erase(bear_fvgs_.begin());
    }

    // ── 5. entries ──
    const bool can_short = s.armed && (s.cisd || !cfg_.req_cisd) && in_trade && flat && short_ok &&
                           trades_today_ < cfg_.max_trades;
    const bool can_long = lg.armed && (lg.cisd || !cfg_.req_cisd) && in_trade && flat && long_ok &&
                          trades_today_ < cfg_.max_trades;

    bool have_signal = false;
    Event signal;

    int hit = -1;
    std::string hit_kind;
    if (s.armed) {
        for (int k = static_cast<int>(s.zones.size()) - 1; k >= 0; --k) {
            const Zone& z = s.zones[k];
            if (c > z.top) {
                s.zones.erase(s.zones.begin() + k);
            } else if (hit < 0 && can_short && z.bar < i && h >= z.bot && c < o) {
                hit = k;
                hit_kind = z.kind;
            }
        }
    }
    if (hit >= 0) {
        const double one = s.ext, zero = s.start, L = one - zero;
        const double stp = one + cfg_.sl_buf_ticks * tick;
        const double t1 = zero + cfg_.tp1_dev * L;
        const double t2 = zero + cfg_.tp2_dev * L;
        const double risk = stp - c;
        const double rr = risk > 0 ? (c - t1) / risk : 0.0;
        if (L > 0 && risk > 0 && rr >= cfg_.min_rr && (cfg_.max_stop_pts == 0 || risk <= cfg_.max_stop_pts)) {
            signal = {"SIGNAL", i, b.ts, -1, c, stp, t1, t2, hit_kind, NaN};
            have_signal = true;
            s.armed = false;
            mm_dir_ = -1;
            mm4_ = zero + (-4.0) * L;
        }
    }

    hit = -1;
    if (lg.armed) {
        for (int k = static_cast<int>(lg.zones.size()) - 1; k >= 0; --k) {
            const Zone& z = lg.zones[k];
            if (c < z.bot) {
                lg.zones.erase(lg.zones.begin() + k);
            } else if (hit < 0 && !have_signal && can_long && z.bar < i && l <= z.top && c > o) {
                hit = k;
                hit_kind = z.kind;
            }
        }
    }
    if (hit >= 0) {
        const double one = lg.ext, zero = lg.start, L = one - zero;
        const double stp = one - cfg_.sl_buf_ticks * tick;
        const double t1 = zero + cfg_.tp1_dev * L;
        const double t2 = zero + cfg_.tp2_dev * L;
        const double risk = c - stp;
        const double rr = risk > 0 ? (t1 - c) / risk : 0.0;
        if (L < 0 && risk > 0 && rr >= cfg_.min_rr && (cfg_.max_stop_pts == 0 || risk <= cfg_.max_stop_pts)) {
            signal = {"SIGNAL", i, b.ts, 1, c, stp, t1, t2, hit_kind, NaN};
            have_signal = true;
            lg.armed = false;
            mm_dir_ = 1;
            mm4_ = zero + (-4.0) * L;
        }
    }

    if (have_signal) {
        events_.push_back(signal);
        pos_ = signal.direction;
        pos_bar_ = i;
        entry_ = c;
        stop_ = signal.stop;
        t1_ = signal.tp1;
        t2_ = signal.tp2;
        risk_ = std::abs(c - signal.stop);
        t1_hit_ = false;
        trade_r_ = 0.0;
        ++trades_today_;
    }

    // ── MMXM switch at -4 STDV ──
    if (mm_dir_ == -1 && l <= mm4_) {
        events_.push_back({"MMXM", i, b.ts, 1, l, NaN, NaN, NaN, "MMSM->MMBM", NaN});
        mm_dir_ = 0;
    }
    if (mm_dir_ == 1 && h >= mm4_) {
        events_.push_back({"MMXM", i, b.ts, -1, h, NaN, NaN, NaN, "MMBM->MMSM", NaN});
        mm_dir_ = 0;
    }

    has_prev_ = true;
    prev_session_ = b.session_date;
    prev_in_acc_ = in_acc;
    return {events_.begin() + static_cast<long>(out_start), events_.end()};
}

void Engine::manage_position(const Bar& b, int i, bool in_flat) {
    const int d = pos_;
    double exit_px = NaN;
    std::string why;
    if (in_flat) {
        exit_px = b.close;
        why = "Flat";
    } else {
        const bool stop_hit = d == 1 ? b.low <= stop_ : b.high >= stop_;
        if (stop_hit) {
            exit_px = stop_;
            why = t1_hit_ ? "BE" : "SL";
        } else {
            const bool t1_reached = d == 1 ? b.high >= t1_ : b.low <= t1_;
            if (!t1_hit_ && t1_reached) {
                t1_hit_ = true;
                trade_r_ += cfg_.tp1_frac * d * (t1_ - entry_) / risk_;
                if (cfg_.tp1_frac >= 1) { exit_px = t1_; why = "TP1"; }
                else if (cfg_.move_be) stop_ = entry_;
            }
            const bool t2_reached = d == 1 ? b.high >= t2_ : b.low <= t2_;
            if (std::isnan(exit_px) && t2_reached) { exit_px = t2_; why = "TP2"; }
        }
    }
    if (!std::isnan(exit_px)) {
        const double rem = t1_hit_ ? (1 - cfg_.tp1_frac) : 1.0;
        trade_r_ += rem * d * (exit_px - entry_) / risk_;
        events_.push_back({"EXIT", i, b.ts, d, exit_px, NaN, NaN, NaN, why, trade_r_});
        pos_ = 0;
    }
}

}  // namespace po3
