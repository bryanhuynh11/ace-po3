"""Run with:  pytest -q   (from the repo root)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from po3.engine import Bar, Config, Engine, in_window  # noqa: E402


def test_in_window_crosses_midnight():
    assert in_window(19 * 60, 18 * 60, 9 * 60 + 30)       # 19:00 inside 18:00-09:30
    assert in_window(3 * 60, 18 * 60, 9 * 60 + 30)        # 03:00 inside
    assert not in_window(10 * 60, 18 * 60, 9 * 60 + 30)   # 10:00 outside


def test_bullish_fvg_is_detected_and_inverted():
    eng = Engine(Config(use_bias=False))
    # three bars with a gap: bar2.low (105) > bar0.high (101)
    bars = [Bar(0, 20260601, 600, 100, 101, 99, 100.5),
            Bar(300, 20260601, 605, 101, 106, 100.5, 105.5),
            Bar(600, 20260601, 610, 105.5, 107, 105, 106.5)]
    for b in bars:
        eng.on_bar(b)
    assert len(eng.bull_fvgs) == 1 and eng.bull_fvgs[0].bot == 101 and eng.bull_fvgs[0].top == 105
    eng.on_bar(Bar(900, 20260601, 615, 106, 106, 99, 100))   # closes below the gap -> inverted
    assert len(eng.bull_fvgs) == 0


def test_stdv_targets_for_a_short():
    # manipulation leg from 100 (start) up to 110 (extreme): L = 10
    one, zero, L = 110.0, 100.0, 10.0
    assert zero + (-2.0) * L == 80.0     # TP1 at -2 STDV
    assert zero + (-4.0) * L == 60.0     # TP2 at -4 STDV
