"""
LEVEL 6: prove the Python and C++ engines agree, event for event.

    python python/compare_engines.py data/nq_5m.csv

This is how real quant teams work: research in Python, production in C++,
and a test that fails loudly if the two ever disagree.
"""
import math
import sys
import time

from cpp_bridge import run_cpp
from po3 import Config, run
from po3.data import load_csv, to_bars


def same(a: float, b: float) -> bool:
    return (math.isnan(a) and math.isnan(b)) or abs(a - b) < 1e-9


def compare(df, cfg: Config, label: str) -> bool:
    t0 = time.perf_counter(); py = run(to_bars(df), cfg); t_py = time.perf_counter() - t0
    t0 = time.perf_counter(); cc = run_cpp(df, cfg); t_cc = time.perf_counter() - t0
    ok = len(py) == len(cc)
    for k, (a, b) in enumerate(zip(py, cc)):
        if not (a.kind == b.kind and a.bar == b.bar and a.direction == b.direction and a.setup == b.setup
                and all(same(getattr(a, f), getattr(b, f)) for f in ("price", "stop", "tp1", "tp2", "r"))):
            print(f"  MISMATCH at event {k}:\n    py : {a}\n    cpp: {b}")
            ok = False
            break
    n_sig = sum(e.kind == "SIGNAL" for e in py)
    print(f"{'PASS' if ok else 'FAIL'}  {label:<28} events={len(py):>5}  signals={n_sig:>3}  "
          f"python={t_py*1000:7.1f} ms  c++={t_cc*1000:6.1f} ms  ({t_py/max(t_cc,1e-9):.0f}x faster)")
    return ok


if __name__ == "__main__":
    df = load_csv(sys.argv[1] if len(sys.argv) > 1 else "data/nq_5m.csv")
    configs = {
        "defaults": Config(),
        "no bias, rr 1.0": Config(use_bias=False, min_rr=1.0),
        "no CISD, wick-to-body": Config(req_cisd=False, sd_wick_to_body=True),
        "TP1 full exit at -1": Config(tp1_dev=-1.0, tp1_frac=1.0, use_bias=False),
        "FVG only, 3 trades/day": Config(use_ifvg=False, use_ob=False, max_trades=3, use_bias=False),
    }
    results = [compare(df, cfg, name) for name, cfg in configs.items()]
    sys.exit(0 if all(results) else 1)
