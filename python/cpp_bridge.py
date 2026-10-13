"""
Glue between Python and the compiled C++ engine (po3cpp).

Build first (from the repo root):
    cmake -S cpp -B cpp/build && cmake --build cpp/build
The module file (po3cpp*.so / .pyd) lands in cpp/build; we add that to sys.path.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd

from po3.engine import Config, Event

BUILD = Path(__file__).resolve().parents[1] / "cpp" / "build"
for p in [BUILD, BUILD / "Release"]:
    if p.exists():
        sys.path.insert(0, str(p))

try:
    import po3cpp
except ImportError as e:  # pragma: no cover
    raise SystemExit("C++ module not built yet. Run: cmake -S cpp -B cpp/build && cmake --build cpp/build") from e


def to_cpp_config(cfg: Config) -> "po3cpp.Config":
    cc = po3cpp.Config()
    for f in dataclasses.fields(cfg):
        setattr(cc, f.name, getattr(cfg, f.name))
    return cc


def run_cpp(df: pd.DataFrame, cfg: Config) -> list[Event]:
    evs = po3cpp.run(to_cpp_config(cfg),
                     df.ts.astype("int64").tolist(), df.session_date.astype(int).tolist(),
                     df.minute.astype(int).tolist(), df.open.tolist(), df.high.tolist(),
                     df.low.tolist(), df.close.tolist())
    return [Event(e.kind, e.bar, e.ts, e.direction, e.price, e.stop, e.tp1, e.tp2, e.setup, e.r) for e in evs]
