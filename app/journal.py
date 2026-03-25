import csv
import os
from datetime import datetime

class TradeJournal:
    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            csv.writer(open(path, "w", newline="", encoding="utf-8")).writerow(
                ["timestamp", "symbol", "action", "qty", "price", "avg_entry_price", "estimated_pl_dollar", "estimated_pl_pct", "account_equity", "buying_power", "reason_summary"]
            )

    def log_trade(self, *row):
        csv.writer(open(self.path, "a", newline="", encoding="utf-8")).writerow([datetime.utcnow().isoformat(), *row])
