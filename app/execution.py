from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

class ExecutionEngine:
    def __init__(self, api_key, api_secret, paper=True, live_trading_enabled=False):
        self.paper = paper
        self.live_trading_enabled = live_trading_enabled
        self.client = TradingClient(api_key, api_secret, paper=paper)

    def get_account(self):
        return self.client.get_account()

    def get_positions_map(self):
        return {p.symbol: p for p in self.client.get_all_positions()}

    def market_buy(self, symbol, qty):
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        if (not self.paper) and (not self.live_trading_enabled):
            raise RuntimeError("Live trading blocked.")
        return self.client.submit_order(
            order_data=MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
        )

    def market_sell(self, symbol, qty):
        if qty <= 0:
            raise ValueError("Quantity must be positive")
        if (not self.paper) and (not self.live_trading_enabled):
            raise RuntimeError("Live trading blocked.")
        return self.client.submit_order(
            order_data=MarketOrderRequest(symbol=symbol, qty=qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
        )
