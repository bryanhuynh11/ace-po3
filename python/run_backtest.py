"""
LEVEL 4: run the PO3 engine over a CSV and print results.

    python python/run_backtest.py data/nq_5m.csv
    python python/run_backtest.py data/nq_5m.csv --engine cpp     # after building C++ (Level 6)
    python python/run_backtest.py data/nq_5m.csv --no-bias --min-rr 1.0

Writes data/trades.csv and data/equity.png.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from po3 import Config, Engine
from po3.backtest import POINT_VALUE, summary, trades_table
from po3.data import load_csv, to_bars

ap = argparse.ArgumentParser()
ap.add_argument("csv")
ap.add_argument("--engine", choices=["python", "cpp"], default="python")
ap.add_argument("--contract", choices=["MNQ", "NQ"], default="MNQ")
ap.add_argument("--contracts", type=int, default=2)
ap.add_argument("--no-bias", action="store_true")
ap.add_argument("--min-rr", type=float, default=1.5)
args = ap.parse_args()

cfg = Config(use_bias=not args.no_bias, min_rr=args.min_rr)
df = load_csv(args.csv)

if args.engine == "python":
    eng = Engine(cfg)
    for b in to_bars(df):
        eng.on_bar(b)
    events = eng.events
else:
    from cpp_bridge import run_cpp
    events = run_cpp(df, cfg)

trades = trades_table(events, POINT_VALUE[args.contract], args.contracts)
stats = summary(trades)
print(f"Engine: {args.engine}   Bars: {len(df):,}   Sweeps: {sum(e.kind == 'SWEEP' for e in events)}")
print(json.dumps(stats, indent=2, default=str))

out_dir = Path(args.csv).resolve().parent
if not trades.empty:
    trades.to_csv(out_dir / "trades.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(trades["exit_time"], trades["R"].cumsum(), marker="o", ms=3)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title("ACE PO3: cumulative R")
    ax.set_ylabel("R")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_dir / "equity.png", dpi=120)
    print(f"Saved {out_dir/'trades.csv'} and {out_dir/'equity.png'}")
