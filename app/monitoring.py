import logging
from prometheus_client import Counter, Gauge, start_http_server

RUNS = Counter("stock_engine_runs_total", "Total starts")
BAR_EVENTS = Counter("stock_engine_bar_events_total", "Bars processed", ["symbol"])
SIGNALS = Counter("stock_engine_signals_total", "Signals", ["symbol", "action"])
LAST_SCORE = Gauge("stock_engine_last_score", "Last score", ["symbol"])

def setup_logging(level="INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    return logging.getLogger("stock_engine")

def start_metrics_server(port):
    start_http_server(port)
