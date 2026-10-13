"""
Turn engine events into a trade list and performance stats.
"""
from __future__ import annotations

import pandas as pd

from .engine import Event

POINT_VALUE = {"NQ": 20.0, "MNQ": 2.0}


def trades_table(events: list[Event], point_value: float = 2.0, contracts: int = 2) -> pd.DataFrame:
    """Pair each SIGNAL with its EXIT. PnL in $ uses R x initial risk."""
    rows, open_sig = [], None
    for ev in events:
        if ev.kind == "SIGNAL":
            open_sig = ev
        elif ev.kind == "EXIT" and open_sig is not None:
            risk_pts = abs(open_sig.price - open_sig.stop)
            rows.append({
                "entry_time": pd.to_datetime(open_sig.ts, unit="s", utc=True).tz_convert("America/New_York"),
                "side": "LONG" if open_sig.direction == 1 else "SHORT",
                "setup": open_sig.setup,
                "entry": open_sig.price, "stop": open_sig.stop,
                "tp1": open_sig.tp1, "tp2": open_sig.tp2,
                "exit_time": pd.to_datetime(ev.ts, unit="s", utc=True).tz_convert("America/New_York"),
                "exit": ev.price, "exit_reason": ev.setup,
                "risk_pts": risk_pts, "R": ev.r,
                "pnl_usd": ev.r * risk_pts * point_value * contracts,
            })
            open_sig = None
    return pd.DataFrame(rows)


def summary(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0}
    r = trades["R"]
    equity = r.cumsum()
    gross_win = r[r > 0].sum()
    gross_loss = -r[r < 0].sum()
    return {
        "trades": len(trades),
        "win_rate_%": round(100 * (r > 0).mean(), 1),
        "avg_R": round(r.mean(), 2),
        "total_R": round(r.sum(), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "max_drawdown_R": round((equity.cummax() - equity).max(), 2),
        "total_pnl_usd": round(trades["pnl_usd"].sum(), 2),
        "by_setup": trades.groupby("setup")["R"].agg(["count", "sum"]).round(2).to_dict("index"),
    }
