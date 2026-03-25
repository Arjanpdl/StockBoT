import json
import os

class RuntimeState:
    def __init__(self, path):
        self.path = path
        self.data = {
            "symbols": {},
            "today": {"date": None, "trades_count": 0, "start_equity": None, "halt_new_entries": False},
            "stats": {"loss_streak": 0},
        }
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                self.data = json.load(open(self.path, "r", encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        json.dump(self.data, open(self.path, "w", encoding="utf-8"), indent=2)

    def get_symbol(self, symbol):
        return self.data["symbols"].setdefault(
            symbol,
            {
                "held_bars": 0,
                "cooldown_bars_left": 0,
                "last_entry_price": None,
                "last_entry_qty": 0,
                "max_close_since_entry": None,
                "partial_taken": False,
            },
        )

    def on_new_bar(self, symbol, has_position, close=None):
        s = self.get_symbol(symbol)
        s["held_bars"] = int(s.get("held_bars", 0)) + 1 if has_position else 0
        if int(s.get("cooldown_bars_left", 0)) > 0:
            s["cooldown_bars_left"] = int(s["cooldown_bars_left"]) - 1
        if has_position and close is not None:
            m = s.get("max_close_since_entry")
            s["max_close_since_entry"] = close if m is None else max(float(m), float(close))

    def start_cooldown(self, symbol, bars):
        self.get_symbol(symbol)["cooldown_bars_left"] = max(0, int(bars))

    def set_entry(self, symbol, price, qty):
        s = self.get_symbol(symbol)
        s["last_entry_price"] = float(price)
        s["last_entry_qty"] = int(qty)
        s["held_bars"] = 0
        s["max_close_since_entry"] = float(price)
        s["partial_taken"] = False

    def mark_partial(self, symbol):
        self.get_symbol(symbol)["partial_taken"] = True

    def clear_entry(self, symbol):
        s = self.get_symbol(symbol)
        s["last_entry_price"] = None
        s["last_entry_qty"] = 0
        s["held_bars"] = 0
        s["max_close_since_entry"] = None
        s["partial_taken"] = False

    def reset_daily_if_needed(self, date_str, equity):
        t = self.data.setdefault("today", {"date": None, "trades_count": 0, "start_equity": None, "halt_new_entries": False})
        if t.get("date") != date_str:
            t["date"] = date_str
            t["trades_count"] = 0
            t["start_equity"] = float(equity)
            t["halt_new_entries"] = False

    def inc_daily_trades(self):
        self.data["today"]["trades_count"] = int(self.data["today"].get("trades_count", 0)) + 1

    def daily_trades(self):
        return int(self.data.setdefault("today", {}).get("trades_count", 0))

    def start_equity(self):
        return self.data.setdefault("today", {}).get("start_equity")

    def halt_entries(self):
        self.data.setdefault("today", {})["halt_new_entries"] = True

    def entries_halted(self):
        return bool(self.data.setdefault("today", {}).get("halt_new_entries", False))

    def loss_streak(self):
        return int(self.data.setdefault("stats", {}).get("loss_streak", 0))

    def record_closed_trade(self, pnl_dollars):
        stats = self.data.setdefault("stats", {})
        stats["loss_streak"] = int(stats.get("loss_streak", 0)) + 1 if pnl_dollars < 0 else 0
