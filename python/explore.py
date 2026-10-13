"""
LEVEL 2: get comfortable with pandas before touching the strategy.

    python python/explore.py data/nq_5m.csv

Things this shows you (read the code, then try the exercises in LEARNING_PATH.md):
  * loading a CSV into a DataFrame
  * filtering rows (NY session only)
  * groupby (one row per trading day)
  * finding fair value gaps with vectorised pandas (no loops)
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

csv = Path(sys.argv[1] if len(sys.argv) > 1 else "data/nq_5m.csv")
df = pd.read_csv(csv)
print(df.head(), "\n")

# 1) NY morning session only (09:30-11:30 = minutes 570-690)
ny = df[(df.minute >= 570) & (df.minute < 690)]
print(f"{len(ny):,} bars inside the 09:30-11:30 kill zone")

# 2) daily range per trading day
daily = df.groupby("session_date").agg(high=("high", "max"), low=("low", "min"))
daily["range"] = daily.high - daily.low
print("\nAverage daily range (points):", round(daily["range"].mean(), 1))

# 3) fair value gaps, vectorised: bullish when low > high two bars ago
df["bull_fvg"] = df.low > df.high.shift(2)
df["bear_fvg"] = df.high < df.low.shift(2)
print("Bullish FVGs:", int(df.bull_fvg.sum()), "  Bearish FVGs:", int(df.bear_fvg.sum()))

# 4) plot the last day of closes
last = df[df.session_date == df.session_date.iloc[-1]]
plt.figure(figsize=(9, 4))
plt.plot(range(len(last)), last.close)
plt.title(f"NQ closes, session {last.session_date.iloc[0]}")
plt.tight_layout()
plt.savefig(csv.parent / "last_day.png", dpi=110)
print("Saved", csv.parent / "last_day.png")
