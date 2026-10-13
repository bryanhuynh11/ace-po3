"""
LEVEL 1: download NQ futures data and save it as a CSV.

    python python/get_data.py              # 5-minute bars, last 60 days
    python python/get_data.py --interval 1m --period 7d

Yahoo Finance is free but limited: 1m bars go back ~7 days, 5m bars ~60 days.
NQ=F is the continuous E-mini Nasdaq contract (MNQ moves exactly the same,
it is just 1/10th the size).
"""
import argparse
from pathlib import Path

import yfinance as yf

from po3.data import add_time_columns

ap = argparse.ArgumentParser()
ap.add_argument("--symbol", default="NQ=F")
ap.add_argument("--interval", default="5m")
ap.add_argument("--period", default="60d")
args = ap.parse_args()

raw = yf.download(args.symbol, interval=args.interval, period=args.period,
                  progress=False, auto_adjust=False, multi_level_index=False)
if raw.empty:
    raise SystemExit("No data came back. Check your internet connection or try again later.")
raw = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()

df = add_time_columns(raw)
out = Path(__file__).resolve().parents[1] / "data" / f"nq_{args.interval}.csv"
out.parent.mkdir(exist_ok=True)
df.to_csv(out, index=False)
print(f"Saved {len(df):,} bars to {out}")
print(df.head())
