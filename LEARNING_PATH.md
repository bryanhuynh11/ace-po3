# Learning path: Python → C++ through one trading project

**Is this too advanced for a beginner?** Not if you go level by level. Each level teaches a small set of skills, ends with something that runs, and has exercises.

How to use it:

- Read the code for a level. Ask Cursor to explain any line you don't understand, then do the exercises *yourself* before asking AI for the answer.
- Commit to git after each level.
- Rough pace: 1–2 weeks per level alongside school.

---

## Level 0: Setup (1 day)

**You learn:** terminal basics, virtual environments, git.

- Follow the Quick start in the README up to `pip install`.
- `git init`, then make your first commit.
- ✅ **Done when:** `python --version` works inside `.venv`.

## Level 1: Get data (`python/get_data.py`)

**You learn:** running scripts, command-line arguments (`argparse`), libraries, files.

- Run it, then open `data/nq_5m.csv` in Cursor and look at the columns.
- **Exercise 1:** Download `MNQ=F` too. Compare the closes with NQ: are they identical?
- **Exercise 2:** Download 1-minute bars (`--interval 1m --period 7d`).

## Level 2: pandas warm-up (`python/explore.py`)

**You learn:** DataFrames, filtering, `groupby`, `shift`, plotting.

- **Exercise 1:** Print the average range of the 09:30–10:00 window versus 10:00–11:30.
- **Exercise 2:** Find each day's overnight high and low (18:00–09:30). On how many days did NY take the overnight high? The low? Both?
- **Exercise 3:** Mark bearish order blocks with pandas: an up candle followed by a candle that closes below its open.
- ✅ **Done when:** you can answer a market question with 5 lines of pandas.

## Level 3: The engine (`python/po3/engine.py`)

**You learn:** classes, dataclasses, state machines, and bar-by-bar ("event-driven") thinking. That last one is how real trading systems work.

- Read `on_bar` top to bottom. Each numbered section matches a step of your PO3 notes.
- Add a `print()` whenever `s.armed` turns True, and watch sweeps → CISD → entries happen in order.
- **Exercise 1:** Add a setting `only_acc_sweeps` that ignores PDH/PDL and swing sweeps.
- **Exercise 2:** Add an *SMT divergence* filter. Load ES data too, and only short when NQ swept a high but ES did not.
- **Exercise 3:** Implement the "valid STDV pull" check from your notes: is there an FVG near the -2 level?
- Run `pytest -q` after every change.

## Level 4: Backtesting (`python/run_backtest.py`, `po3/backtest.py`)

**You learn:** turning signals into statistics, R-multiples, drawdown, and why overfitting is dangerous.

- Run the backtest with and without `--no-bias`. What changes?
- **Exercise 1:** Add an "expectancy per setup type" table. Which works best: FVG, iFVG or OB?
- **Exercise 2:** Do a parameter sweep. Loop `min_rr` over [1, 1.5, 2, 3] and print total R for each.
- **Exercise 3 (important):** Split the data into the first 40 days and the last 20. Tune on the first part and test on the second. Does the edge survive?

## Level 5: C++ (`cpp/`)

**You learn:** compiling, headers vs source files, `struct`/`class`, `std::vector`, references (`&`), `const`, CMake.

- Build and run `po3_cli`. Then put `engine.py` and `engine.cpp` side by side in Cursor and match them up section by section.
- Key differences to notice:
  - C++ needs types: `double`, `int`, `bool`.
  - Python's `None` becomes `NaN` here.
  - `list.remove` becomes `erase`.
  - `Setup& s = short_;` means `s` *is* `short_` (a reference), not a copy.
- **Exercise 1:** Add a `--min-rr 2.0` command-line flag to `main.cpp`.
- **Exercise 2:** Make `po3_cli` write `trades.csv`.
- **Exercise 3:** Port your Level 3 changes to C++, then run `compare_engines.py` until it says PASS.

## Level 6: Python + C++ together (`bindings/`, `compare_engines.py`)

**You learn:** pybind11, testing one implementation against another, and measuring performance.

- This is the core quant workflow: **research in Python, production in C++, and a test that keeps them identical.**
- **Exercise 1:** Add `cfg.max_stop_pts` to the CLI and the comparison configs.
- **Exercise 2:** Profile the code. Where does Python spend its time? (`python -m cProfile -s cumtime python/run_backtest.py data/nq_5m.csv`)

## Level 7: Stretch goals (portfolio level)

- Live mode: stream bars from a broker or data API into `Engine.on_bar` and push alerts to your phone.
- Rewrite the leg lookback with a monotonic deque so it runs in O(1) per bar. This is a classic interview topic.
- Add unit tests in C++ with GoogleTest.
- Write up results honestly in the README, including the out-of-sample test. That's what recruiters look for.

---

### Python ↔ C++ cheat sheet

| Python | C++ |
|---|---|
| `x = 5` | `int x = 5;` |
| `xs = []` / `xs.append(v)` | `std::vector<double> xs;` / `xs.push_back(v);` |
| `math.nan`, `math.isnan(x)` | `NaN`, `std::isnan(x)` |
| `@dataclass class Bar:` | `struct Bar { ... };` |
| `def f(self, b: Bar) -> list[Event]:` | `std::vector<Event> f(const Bar& b);` |
| `for z in reversed(zones):` | `for (int k = zones.size() - 1; k >= 0; --k)` |
| `a and b or not c` | `a && b \|\| !c` |
| `x if cond else y` | `cond ? x : y` |
