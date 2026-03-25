from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

def _csv(name: str, default: str) -> list[str]:
    return [x.strip().upper() for x in os.getenv(name, default).split(",") if x.strip()]

@dataclass
class Settings:
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_api_secret: str = os.getenv("ALPACA_API_SECRET", "")
    trading_mode: str = os.getenv("TRADING_MODE", "paper").lower().strip()
    live_trading_enabled: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    data_feed: str = os.getenv("DATA_FEED", "iex").lower().strip()

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "").strip()
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "").strip()

    benchmark_symbol: str = os.getenv("BENCHMARK_SYMBOL", "SPY").upper().strip()
    second_benchmark_symbol: str = os.getenv("SECOND_BENCHMARK_SYMBOL", "QQQ").upper().strip()
    watchlist: list[str] | None = None

    risk_per_trade: float = float(os.getenv("RISK_PER_TRADE", "0.002"))
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "0.05"))
    atr_multiplier: float = float(os.getenv("ATR_MULTIPLIER", "2.5"))
    min_stop_pct: float = float(os.getenv("MIN_STOP_PCT", "0.02"))
    min_hold_bars: int = int(os.getenv("MIN_HOLD_BARS", "15"))
    cooldown_bars: int = int(os.getenv("COOLDOWN_BARS", "30"))
    max_trades_per_day: int = int(os.getenv("MAX_TRADES_PER_DAY", "2"))
    max_daily_loss_pct: float = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.008"))

    no_trade_first_minutes: int = int(os.getenv("NO_TRADE_FIRST_MINUTES", "20"))
    no_trade_last_minutes: int = int(os.getenv("NO_TRADE_LAST_MINUTES", "30"))
    trade_extended_hours: bool = os.getenv("TRADE_EXTENDED_HOURS", "false").lower() == "true"

    stale_data_seconds: int = int(os.getenv("STALE_DATA_SECONDS", "180"))
    heartbeat_seconds: int = int(os.getenv("HEARTBEAT_SECONDS", "300"))
    quiet_heartbeat: bool = os.getenv("QUIET_HEARTBEAT", "true").lower() == "true"
    smart_heartbeat_alerts: bool = os.getenv("SMART_HEARTBEAT_ALERTS", "true").lower() == "true"
    heartbeat_summary_every_n: int = int(os.getenv("HEARTBEAT_SUMMARY_EVERY_N", "6"))
    send_market_closed_alert: bool = os.getenv("SEND_MARKET_CLOSED_ALERT", "false").lower() == "true"
    send_recovery_alert: bool = os.getenv("SEND_RECOVERY_ALERT", "true").lower() == "true"

    allow_partial_profit: bool = os.getenv("ALLOW_PARTIAL_PROFIT", "true").lower() == "true"
    overextension_pct: float = float(os.getenv("OVEREXTENSION_PCT", "0.03"))

    enable_news_filter: bool = os.getenv("ENABLE_NEWS_FILTER", "true").lower() == "true"
    enable_news_alerts: bool = os.getenv("ENABLE_NEWS_ALERTS", "true").lower() == "true"
    enable_news_alpha_alerts: bool = os.getenv("ENABLE_NEWS_ALPHA_ALERTS", "true").lower() == "true"
    news_lookback_hours: int = int(os.getenv("NEWS_LOOKBACK_HOURS", "12"))
    news_poll_seconds: int = int(os.getenv("NEWS_POLL_SECONDS", "900"))
    negative_news_block_score: int = int(os.getenv("NEGATIVE_NEWS_BLOCK_SCORE", "-25"))
    positive_news_bonus_score: int = int(os.getenv("POSITIVE_NEWS_BONUS_SCORE", "8"))
    require_positive_news_for_buy: bool = os.getenv("REQUIRE_POSITIVE_NEWS_FOR_BUY", "false").lower() == "true"
    news_alpha_min_score: int = int(os.getenv("NEWS_ALPHA_MIN_SCORE", "18"))

    volume_confirm_ratio: float = float(os.getenv("VOLUME_CONFIRM_RATIO", "1.3"))
    high_conviction_volume_ratio: float = float(os.getenv("HIGH_CONVICTION_VOLUME_RATIO", "2.0"))

    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
    max_loss_streak: int = int(os.getenv("MAX_LOSS_STREAK", "3"))
    min_dollar_volume: float = float(os.getenv("MIN_DOLLAR_VOLUME", "5000000"))
    max_gap_pct: float = float(os.getenv("MAX_GAP_PCT", "0.08"))
    time_stop_bars: int = int(os.getenv("TIME_STOP_BARS", "30"))
    time_stop_min_r: float = float(os.getenv("TIME_STOP_MIN_R", "0.3"))
    require_relative_strength: bool = os.getenv("REQUIRE_RELATIVE_STRENGTH", "false").lower() == "true"

    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    metrics_port: int = int(os.getenv("METRICS_PORT", "8010"))
    trade_journal_csv: str = os.getenv("TRADE_JOURNAL_CSV", "trade_journal.csv")
    state_json: str = os.getenv("STATE_JSON", "runtime_state.json")
    news_db_path: str = os.getenv("NEWS_DB_PATH", "news_alerts.db")

    def __post_init__(self):
        self.watchlist = _csv("WATCHLIST", "NVDA,AMD,MSFT,AAPL,META,AVGO,AMZN,GOOGL,TSLA,PLTR")
        self.watchlist = [s for s in self.watchlist if s not in {self.benchmark_symbol, self.second_benchmark_symbol}]

    @property
    def paper(self) -> bool:
        return self.trading_mode == "paper"

    def validate(self) -> None:
        miss = [k for k, v in {
            "ALPACA_API_KEY": self.alpaca_api_key,
            "ALPACA_API_SECRET": self.alpaca_api_secret,
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
            "TELEGRAM_CHAT_ID": self.telegram_chat_id,
        }.items() if not v]
        if miss:
            raise ValueError("Missing: " + ", ".join(miss))
