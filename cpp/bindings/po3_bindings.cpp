// LEVEL 6: expose the C++ engine to Python with pybind11.
// After building, Python can do:  import po3cpp; eng = po3cpp.Engine(po3cpp.Config())
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "po3/engine.hpp"

namespace py = pybind11;
using namespace po3;

PYBIND11_MODULE(po3cpp, m) {
    m.doc() = "ACE PO3 engine (C++)";

    py::class_<Config>(m, "Config")
        .def(py::init<>())
        .def_readwrite("trade_start", &Config::trade_start)
        .def_readwrite("trade_end", &Config::trade_end)
        .def_readwrite("acc_start", &Config::acc_start)
        .def_readwrite("acc_end", &Config::acc_end)
        .def_readwrite("flat_start", &Config::flat_start)
        .def_readwrite("flat_end", &Config::flat_end)
        .def_readwrite("use_acc", &Config::use_acc)
        .def_readwrite("use_pd", &Config::use_pd)
        .def_readwrite("use_piv", &Config::use_piv)
        .def_readwrite("piv_len", &Config::piv_len)
        .def_readwrite("leg_look", &Config::leg_look)
        .def_readwrite("max_wait", &Config::max_wait)
        .def_readwrite("use_fvg", &Config::use_fvg)
        .def_readwrite("use_ifvg", &Config::use_ifvg)
        .def_readwrite("use_ob", &Config::use_ob)
        .def_readwrite("req_cisd", &Config::req_cisd)
        .def_readwrite("min_gap_ticks", &Config::min_gap_ticks)
        .def_readwrite("tick", &Config::tick)
        .def_readwrite("sd_wick_to_body", &Config::sd_wick_to_body)
        .def_readwrite("tp1_dev", &Config::tp1_dev)
        .def_readwrite("tp2_dev", &Config::tp2_dev)
        .def_readwrite("tp1_frac", &Config::tp1_frac)
        .def_readwrite("move_be", &Config::move_be)
        .def_readwrite("sl_buf_ticks", &Config::sl_buf_ticks)
        .def_readwrite("min_rr", &Config::min_rr)
        .def_readwrite("max_stop_pts", &Config::max_stop_pts)
        .def_readwrite("max_trades", &Config::max_trades)
        .def_readwrite("use_bias", &Config::use_bias)
        .def_readwrite("bias_thr_atr", &Config::bias_thr_atr)
        .def_readwrite("atr_len", &Config::atr_len);

    py::class_<Bar>(m, "Bar")
        .def(py::init<>())
        .def(py::init([](int64_t ts, int sd, int minute, double o, double h, double l, double c) {
            return Bar{ts, sd, minute, o, h, l, c};
        }))
        .def_readwrite("ts", &Bar::ts)
        .def_readwrite("session_date", &Bar::session_date)
        .def_readwrite("minute", &Bar::minute)
        .def_readwrite("open", &Bar::open)
        .def_readwrite("high", &Bar::high)
        .def_readwrite("low", &Bar::low)
        .def_readwrite("close", &Bar::close);

    py::class_<Event>(m, "Event")
        .def_readonly("kind", &Event::kind)
        .def_readonly("bar", &Event::bar)
        .def_readonly("ts", &Event::ts)
        .def_readonly("direction", &Event::direction)
        .def_readonly("price", &Event::price)
        .def_readonly("stop", &Event::stop)
        .def_readonly("tp1", &Event::tp1)
        .def_readonly("tp2", &Event::tp2)
        .def_readonly("setup", &Event::setup)
        .def_readonly("r", &Event::r);

    py::class_<Engine>(m, "Engine")
        .def(py::init<Config>(), py::arg("cfg") = Config())
        .def("on_bar", &Engine::on_bar)
        .def("events", &Engine::events)
        .def_property_readonly("bias", &Engine::bias)
        .def_property_readonly("position", &Engine::position);

    // Fast path: run a whole dataset in one call (no Python loop per bar).
    m.def("run", [](const Config& cfg, const std::vector<int64_t>& ts, const std::vector<int>& sd,
                    const std::vector<int>& minute, const std::vector<double>& o, const std::vector<double>& h,
                    const std::vector<double>& l, const std::vector<double>& c) {
        Engine eng(cfg);
        for (size_t k = 0; k < ts.size(); ++k) eng.on_bar(Bar{ts[k], sd[k], minute[k], o[k], h[k], l[k], c[k]});
        return eng.events();
    });
}
