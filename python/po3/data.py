"""
Loading NQ data and turning it into Bar objects.

Every CSV in this project has the same columns, so Python and C++ read the
exact same file:

    ts,session_date,minute,open,high,low,close,volume

ts            unix seconds (UTC)
session_date  CME trading day, YYYYMMDD. Futures trade from 18:00 ET the
              evening before, so a 19:00 ET Sunday bar belongs to Monday.
minute        minutes after midnight in New York time (09:30 -> 570)
"""
from __future__ import annotations

import pandas as pd

from .engine import Bar

NY = "America/New_York"
COLUMNS = ["ts", "session_date", "minute", "open", "high", "low", "close", "volume"]


def add_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """df has a DatetimeIndex and open/high/low/close/volume columns."""
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    ny = idx.tz_convert(NY)
    out = pd.DataFrame(index=range(len(df)))
    out["ts"] = (idx.tz_convert("UTC").asi8 // 1_000_000_000).astype("int64")
    # bars at/after 18:00 ET belong to the next trading day
    trade_day = (ny + pd.to_timedelta((ny.hour >= 18).astype(int), unit="D")).normalize()
    out["session_date"] = trade_day.strftime("%Y%m%d").astype(int)
    out["minute"] = ny.hour * 60 + ny.minute
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = df[col].to_numpy()
    return out[COLUMNS]


def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def to_bars(df: pd.DataFrame) -> list[Bar]:
    return [
        Bar(int(r.ts), int(r.session_date), int(r.minute),
            float(r.open), float(r.high), float(r.low), float(r.close))
        for r in df.itertuples(index=False)
    ]
