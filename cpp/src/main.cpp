// LEVEL 5: command-line runner.
//
//   ./build/po3_cli ../data/nq_5m.csv            prints signals + summary
//   ./build/po3_cli ../data/nq_5m.csv --events   prints every event (sweeps, MMXM, exits)
//
// It reads the same CSV the Python code uses:
//   ts,session_date,minute,open,high,low,close,volume
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "po3/engine.hpp"

static std::vector<po3::Bar> load_csv(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open " + path);
    std::vector<po3::Bar> bars;
    std::string line;
    std::getline(in, line);  // skip header
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line);
        std::string f;
        po3::Bar b;
        std::getline(ss, f, ','); b.ts = std::stoll(f);
        std::getline(ss, f, ','); b.session_date = std::stoi(f);
        std::getline(ss, f, ','); b.minute = std::stoi(f);
        std::getline(ss, f, ','); b.open = std::stod(f);
        std::getline(ss, f, ','); b.high = std::stod(f);
        std::getline(ss, f, ','); b.low = std::stod(f);
        std::getline(ss, f, ','); b.close = std::stod(f);
        bars.push_back(b);
    }
    return bars;
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: po3_cli <bars.csv> [--events]\n";
        return 1;
    }
    const bool all_events = argc > 2 && std::string(argv[2]) == "--events";

    std::vector<po3::Bar> bars;
    try {
        bars = load_csv(argv[1]);
    } catch (const std::exception& e) {
        std::cerr << e.what() << "\n";
        return 1;
    }

    po3::Engine engine;  // default Config: same defaults as Python
    const auto t0 = std::chrono::steady_clock::now();
    for (const auto& b : bars) engine.on_bar(b);
    const auto us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();

    int trades = 0, wins = 0;
    double total_r = 0.0;
    for (const auto& e : engine.events()) {
        const bool show = all_events || e.kind == "SIGNAL" || e.kind == "EXIT";
        if (show) {
            std::printf("%-6s bar=%-6d %-5s %-5s price=%.2f", e.kind.c_str(), e.bar,
                        e.direction == 1 ? "LONG" : "SHORT", e.setup.c_str(), e.price);
            if (e.kind == "SIGNAL") std::printf("  stop=%.2f tp1=%.2f tp2=%.2f", e.stop, e.tp1, e.tp2);
            if (e.kind == "EXIT") std::printf("  R=%+.2f", e.r);
            std::printf("\n");
        }
        if (e.kind == "EXIT") {
            ++trades;
            total_r += e.r;
            if (e.r > 0) ++wins;
        }
    }
    std::printf("\nBars: %zu   Trades: %d   Win rate: %.1f%%   Total R: %+.2f\n", bars.size(), trades,
                trades ? 100.0 * wins / trades : 0.0, total_r);
    std::printf("Engine time: %lld us (%.2f us per bar)\n", static_cast<long long>(us),
                bars.empty() ? 0.0 : static_cast<double>(us) / bars.size());
    return 0;
}
