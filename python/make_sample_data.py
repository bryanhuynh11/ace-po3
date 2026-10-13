"""
Make fake-but-realistic NQ 5-minute bars, so you can test the code offline.

    python python/make_sample_data.py --days 60

It is a random walk with NQ-like volatility (busier at the 09:30 open),
plus occasional "stop runs" that sweep a level and snap back, so the engine
has PO3-style moves to find. Do NOT judge the strategy on this data. Use
real data from get_data.py for that.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from po3.data import add_time_columns

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=60)
ap.add_argument("--seed", type=int, default=7)
args = ap.parse_args()
rng = np.random.default_rng(args.seed)

idx = pd.date_range("2026-06-01", periods=args.days * 288, freq="5min", tz="America/New_York")
idx = idx[(idx.dayofweek < 5) & ~((idx.hour == 17))]           # skip weekends + 17:00 maintenance hour
mins = idx.hour * 60 + idx.minute
vol = np.where((mins >= 570) & (mins < 690), 9.0, np.where((mins >= 180) & (mins < 570), 5.0, 3.0))

price = 21000.0
rows, drift = [], 0.0
for v in vol:
    if rng.random() < 0.01:                                     # start a stop run
        drift = rng.choice([-1, 1]) * v * 1.5
    move = rng.normal(drift, v)
    drift *= -0.6 if abs(drift) > 0 and rng.random() < 0.35 else 0.85
    o = price
    c = o + move
    hi = max(o, c) + abs(rng.normal(0, v * 0.5))
    lo = min(o, c) - abs(rng.normal(0, v * 0.5))
    rows.append((round(o * 4) / 4, round(hi * 4) / 4, round(lo * 4) / 4, round(c * 4) / 4, int(rng.integers(500, 5000))))
    price = c

df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx.tz_convert("UTC"))
df["high"] = df[["open", "high", "close"]].max(axis=1)
df["low"] = df[["open", "low", "close"]].min(axis=1)
out = Path(__file__).resolve().parents[1] / "data" / "sample_5m.csv"
out.parent.mkdir(exist_ok=True)
add_time_columns(df).to_csv(out, index=False)
print(f"Saved {len(df):,} synthetic bars to {out}")
