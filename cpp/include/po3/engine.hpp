// ACE PO3 engine: C++ version.
//
// This is a line-by-line translation of python/po3/engine.py.
// Python is where you explore ideas; C++ is where you make them fast.
// `python python/compare_engines.py` proves both produce identical signals.
#pragma once

#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace po3 {

// NaN = "no value yet" (same as Pine's na). Any comparison with NaN is false.
inline constexpr double NaN = std::numeric_limits<double>::quiet_NaN();

struct Config {
    // Sessions: minutes after midnight, New York time
    int trade_start = 9 * 60 + 30;
    int trade_end = 11 * 60 + 30;
    int acc_start = 18 * 60;
    int acc_end = 9 * 60 + 30;
    int flat_start = 15 * 60 + 55;
    int flat_end = 18 * 60;

    // Manipulation (liquidity sweeps)
    bool use_acc = true;
    bool use_pd = true;
    bool use_piv = true;
    int piv_len = 5;
    int leg_look = 20;
    int max_wait = 30;

    // PD array entries
    bool use_fvg = true;
    bool use_ifvg = true;
    bool use_ob = true;
    bool req_cisd = true;
    int min_gap_ticks = 2;
    double tick = 0.25;

    // Standard deviations
    bool sd_wick_to_body = false;
    double tp1_dev = -2.0;
    double tp2_dev = -4.0;
    double tp1_frac = 0.5;
    bool move_be = true;

    // Risk
    int sl_buf_ticks = 4;
    double min_rr = 1.5;
    double max_stop_pts = 0.0;
    int max_trades = 2;

    // Bias
    bool use_bias = true;
    double bias_thr_atr = 0.5;
    int atr_len = 14;
};

struct Bar {
    int64_t ts = 0;          // unix seconds UTC
    int session_date = 0;    // YYYYMMDD CME trading day
    int minute = 0;          // minutes after midnight, New York
    double open = 0, high = 0, low = 0, close = 0;
};

struct Zone {
    double top = NaN;
    double bot = NaN;
    int bar = 0;
    std::string kind;        // "FVG", "iFVG", "OB"
};

struct Setup {
    bool armed = false;
    int bar = 0;
    double ext = NaN;        // STDV "1"
    double start = NaN;      // STDV "0"
    bool cisd = false;
    std::vector<Zone> zones;
};

struct Event {
    std::string kind;        // "SWEEP", "SIGNAL", "EXIT", "MMXM"
    int bar = 0;
    int64_t ts = 0;
    int direction = 0;       // +1 long, -1 short
    double price = NaN;
    double stop = NaN;
    double tp1 = NaN;
    double tp2 = NaN;
    std::string setup;
    double r = NaN;
};

bool in_window(int minute, int start, int end);

class Engine {
public:
    explicit Engine(Config cfg = {});

    // Feed one bar. Returns the events produced on this bar.
    std::vector<Event> on_bar(const Bar& b);

    const std::vector<Event>& events() const { return events_; }
    int bias() const { return bias_; }
    int position() const { return pos_; }

private:
    void update_atr(int i);
    void pivots(int i, double& ph, double& pl) const;
    void manage_position(const Bar& b, int i, bool in_flat);

    Config cfg_;
    std::vector<double> o_, h_, l_, c_;
    bool has_prev_ = false;
    int prev_session_ = 0;
    bool prev_in_acc_ = false;

    double atr_ = NaN;
    std::vector<double> tr_seed_;

    double acc_hi_ = NaN, acc_lo_ = NaN;
    bool acc_hi_taken_ = false, acc_lo_taken_ = false;
    double sess_hi_ = NaN, sess_lo_ = NaN;
    double pdh_ = NaN, pdl_ = NaN;
    bool pdh_taken_ = false, pdl_taken_ = false;
    double sw_hi_ = NaN, sw_lo_ = NaN;
    bool sw_hi_taken_ = false, sw_lo_taken_ = false;

    long long htf_key_ = -1;
    double h_o_ = NaN, h_h_ = NaN, h_l_ = NaN;
    int bias_ = 0;

    std::vector<Zone> bull_fvgs_, bear_fvgs_;

    double up_run_open_ = NaN, up_run_high_ = NaN;
    double dn_run_open_ = NaN, dn_run_low_ = NaN;

    Setup short_, long_;

    int pos_ = 0;
    int pos_bar_ = 0;
    double entry_ = NaN, stop_ = NaN, t1_ = NaN, t2_ = NaN, risk_ = NaN;
    bool t1_hit_ = false;
    double trade_r_ = 0.0;
    int trades_today_ = 0;

    int mm_dir_ = 0;
    double mm4_ = NaN;

    std::vector<Event> events_;
};

}  // namespace po3
