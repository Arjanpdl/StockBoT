from datetime import datetime, timedelta, timezone
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

def parse_data_feed(feed):
    return DataFeed.IEX if (feed or "iex").strip().lower() == "iex" else DataFeed.SIP

class AlpacaDataProvider:
    def __init__(self, api_key, api_secret, feed="iex"):
        self.historical = StockHistoricalDataClient(api_key, api_secret)
        self.feed = parse_data_feed(feed)
        self.stream = StockDataStream(api_key, api_secret, feed=self.feed)

    def get_recent_bars(self, symbols, limit=500, timeframe=None):
        timeframe = timeframe or TimeFrame(1, TimeFrameUnit.Minute)
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=timeframe,
            start=datetime.now(timezone.utc) - timedelta(days=10),
            feed=self.feed,
        )
        bars = self.historical.get_stock_bars(req)
        df = bars.df.reset_index()
        out = {}
        if df.empty:
            return {s: pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]) for s in symbols}
        for s in symbols:
            sdf = df[df["symbol"] == s].copy()
            out[s] = sdf[["timestamp", "open", "high", "low", "close", "volume"]].tail(limit).reset_index(drop=True) if not sdf.empty else pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        return out

    @staticmethod
    def append_bar(df, bar):
        row = {
            "timestamp": pd.to_datetime(getattr(bar, "timestamp")),
            "open": float(getattr(bar, "open")),
            "high": float(getattr(bar, "high")),
            "low": float(getattr(bar, "low")),
            "close": float(getattr(bar, "close")),
            "volume": float(getattr(bar, "volume")),
        }
        if df.empty:
            return pd.DataFrame([row])
        if pd.to_datetime(df.iloc[-1]["timestamp"]) == row["timestamp"]:
            df.iloc[-1] = row
            return df
        return pd.concat([df, pd.DataFrame([row])], ignore_index=True).tail(800).reset_index(drop=True)
