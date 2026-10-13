# ACE PO3: an ICT signal engine in Python and C++

This project turns your ICT notes into code. It covers Power of 3, STDV, PD arrays (FVG, iFVG, OB), OHLC/OLHC bias and MMXM, and it trades NQ/MNQ in the New York session. The same engine exists twice:

| | Python (`python/po3/engine.py`) | C++ (`cpp/src/engine.cpp`) |
|---|---|---|
| Purpose | research, backtesting, learning | speed, production-style code |
| Speed (12k bars) | ~200 ms | ~10 ms (about 20× faster) |
| Proof they match | `python python/compare_engines.py` | ← same test |

The same setup is also in `tradingview/` as a Pine Script version, if you want to see it on a chart.

**New to Python or C++?** Start with [`LEARNING_PATH.md`](LEARNING_PATH.md). It walks through the project in 7 levels.

## Quick start (Mac)

```bash
# one-time tools
xcode-select --install            # C++ compiler (clang)
brew install cmake                # build tool (install Homebrew first from brew.sh)

# project setup
cd ace-po3
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Level 1: download real NQ data (5-minute bars, last 60 days)
python python/get_data.py

# Level 4: backtest in Python
python python/run_backtest.py data/nq_5m.csv

# Level 5/6: build C++, run it, prove it matches Python
cmake -S cpp -B cpp/build && cmake --build cpp/build
./cpp/build/po3_cli data/nq_5m.csv
python python/compare_engines.py data/nq_5m.csv

# tests
pytest -q
```

No internet? Run `python python/make_sample_data.py` to make fake NQ bars in `data/sample_5m.csv`. They're good for testing the code but **not** for judging the strategy.

## Project layout

```
ace-po3/
├── LEARNING_PATH.md        ← start here
├── python/
│   ├── get_data.py         L1  download NQ from Yahoo Finance
│   ├── explore.py          L2  pandas warm-up
│   ├── po3/engine.py       L3  the strategy, bar by bar (reference version)
│   ├── po3/backtest.py     L4  trades table + stats
│   ├── run_backtest.py     L4  command-line backtest
│   ├── cpp_bridge.py       L6  calls the C++ engine from Python
│   └── compare_engines.py  L6  Python vs C++ parity check
├── cpp/
│   ├── include/po3/engine.hpp   L5  types + Engine class
│   ├── src/engine.cpp           L5  the strategy in C++
│   ├── src/main.cpp             L5  command-line runner
│   ├── bindings/po3_bindings.cpp L6 pybind11 module
│   └── CMakeLists.txt
├── tests/test_engine.py
└── tradingview/            Pine Script bot + indicator
```

## Using Cursor

1. Open the `ace-po3` folder in Cursor.
2. Install these extensions: **Python**, **clangd** and **CMake Tools**.
3. After the first CMake build, `cpp/build/compile_commands.json` exists. clangd uses it for autocomplete and error checking.
4. Select the `.venv` interpreter: Cmd+Shift+P → "Python: Select Interpreter".

## Data notes

- Yahoo `NQ=F` is the continuous front-month contract. Free history is limited: 1-minute bars go back about 7 days and 5-minute bars about 60 days. For years of data you'd need a paid feed like Databento, FirstRate Data or Kibot. Export it to the same CSV columns and everything else still works.
- CSV format: `ts,session_date,minute,open,high,low,close,volume`. `minute` is New York time, and `session_date` is the CME trading day, which starts at 18:00 ET.

## Honest caveats

- The backtest fills orders at signal-bar close and checks the stop before targets inside a bar. That's conservative, but it isn't tick-accurate.
- 60 days of 5-minute data is a small sample. Treat results as a sanity check, not as proof of an edge.
- This is for education and research only, not financial advice.
