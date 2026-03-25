import threading
import time
import os

from app.config import Settings
from app.data_provider import AlpacaDataProvider
from app.execution import ExecutionEngine
from app.indicators import add_indicators
from app.monitoring import setup_logging, start_metrics_server, RUNS, BAR_EVENTS, SIGNALS, LAST_SCORE
from app.notifier import TelegramNotifier
from app.portfolio import compute_position_size
from app.strategy import FinalOptimizedStrategy
from app.state import RuntimeState
from app.journal import TradeJournal
from app.time_utils import now_et, is_regular_market_hours, in_no_trade_zone
from app.news_engine import NewsEngine

def main():
    s = Settings()
    s.validate()

    logger = setup_logging(s.log_level)
    start_metrics_server(s.metrics_port)
    RUNS.inc()

    notifier = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    provider = AlpacaDataProvider(s.alpaca_api_key, s.alpaca_api_secret, feed=s.data_feed)
    executor = ExecutionEngine(s.alpaca_api_key, s.alpaca_api_secret, paper=s.paper, live_trading_enabled=s.live_trading_enabled)
    strategy = FinalOptimizedStrategy(
        s.atr_multiplier, s.min_stop_pct, s.overextension_pct, s.volume_confirm_ratio,
        s.high_conviction_volume_ratio, s.min_dollar_volume, s.max_gap_pct,
        s.require_relative_strength, s.time_stop_bars, s.time_stop_min_r,
    )
    state = RuntimeState(s.state_json)
    journal = TradeJournal(s.trade_journal_csv)
    news = NewsEngine(s.finnhub_api_key, "", s.sec_user_agent, s.news_db_path)
    account = executor.get_account()
    logger.info("Booting bot | mode=%s | watchlist=%s", "paper" if s.paper else "live", ",".join(s.watchlist))
    notifier.send(
    f"🚀 Bot started\n"
    f"Build: V6.6 Final Optimized\n"
    f"Mode: {'PAPER' if s.paper else 'LIVE'}\n"
    f"Equity: ${float(account.equity):,.2f}\n"
    f"Buying power: ${float(account.buying_power):,.2f}\n"
    f"Watchlist: {', '.join(s.watchlist[:10])}...\n"
    f"Risk/trade: {s.risk_per_trade:.3%}\n"
    f"Max trades/day: {s.max_trades_per_day}\n"
    f"Max positions: {s.max_open_positions}\n"
    f"News+SEC: {'ON' if s.enable_news_filter else 'OFF'}\n"
    f"Heartbeat: {s.heartbeat_seconds}s"
    )

    symbols = s.watchlist + [s.benchmark_symbol, s.second_benchmark_symbol]
    frames = {k: add_indicators(v) for k, v in provider.get_recent_bars(symbols, limit=500).items()}
    last_alert = {}
    rt = {
        "last_bar_epoch": time.time(),
        "last_bar_ts": None,
        "last_news_poll": 0,
        "recovery_sent": False,
        "stale_sent": False,
        "hb_count": 0,
        "bars_seen": 0,
        "closed_sent": False,
    }
    news_cache = {}

    def can_alert(key, value):
        if last_alert.get(key) == value:
            return False
        last_alert[key] = value
        return True

    def refresh_news(force=False):
        if (not force) and time.time() - rt["last_news_poll"] < s.news_poll_seconds:
            return
        rt["last_news_poll"] = time.time()
        logger.info("Refreshing news/SEC scan")
        for sym in s.watchlist:
            try:
                assess = news.assess_symbol(sym, s.news_lookback_hours)
                news_cache[sym] = assess
                logger.info("News scan | %s | priority=%s | score=%s", sym, assess.priority, assess.bias_score)
                fp = f"{assess.priority}:{assess.bias_score}:{'|'.join(assess.top_titles)}"
                if s.enable_news_alerts and assess.priority in {"BREAKING", "HIGH", "WARNING"} and can_alert(sym + "_NEWS", fp):
                    icon = {"BREAKING": "🟢 BREAKING POSITIVE", "HIGH": "🟢 HIGH PRIORITY", "WARNING": "🔴 WARNING"}[assess.priority]
                    msg = [f"{icon} — {sym}", f"Headline/SEC score: {assess.bias_score}", "Why it matters:"]
                    for line in assess.summary_lines[:4]:
                        msg.append(f"- {line}")
                    if assess.sec_hits:
                        msg.append("SEC findings:")
                        for line in assess.sec_hits[:3]:
                            msg.append(f"- {line}")
                    if assess.top_titles:
                        msg.append("Top items:")
                        for t in assess.top_titles[:3]:
                            msg.append(f"- {t}")
                    notifier.send("\n".join(msg))
            except Exception as e:
                logger.warning("News refresh failed for %s: %s", sym, e)

    async def handle_bar(bar):
        sym = getattr(bar, "symbol", None) or getattr(bar, "S", None)
        if not sym:
            return
        dt = getattr(bar, "timestamp").astimezone(now_et().tzinfo)
        rt["last_bar_epoch"] = time.time()
        rt["last_bar_ts"] = str(getattr(bar, "timestamp"))
        rt["bars_seen"] += 1

        if rt["stale_sent"] and s.smart_heartbeat_alerts and s.send_recovery_alert and not rt["recovery_sent"]:
            try:
                notifier.send(f"✅ Stream recovered\nLast bar: {rt['last_bar_ts']}")
                rt["recovery_sent"] = True
                rt["stale_sent"] = False
            except Exception:
                pass

        if (not s.trade_extended_hours) and (not is_regular_market_hours(dt)):
            return

        frames[sym] = add_indicators(provider.append_bar(frames[sym], bar))
        if sym in {s.benchmark_symbol, s.second_benchmark_symbol}:
            return

        logger.info("Bar | %s | close=%.2f volume=%.0f", sym, float(getattr(bar, "close")), float(getattr(bar, "volume")))
        BAR_EVENTS.labels(symbol=sym).inc()

        acc = executor.get_account()
        equity = float(acc.equity)
        buying_power = float(acc.buying_power)

        state.reset_daily_if_needed(dt.strftime("%Y-%m-%d"), equity)
        start_equity = state.start_equity() or equity
        if equity <= start_equity * (1.0 - s.max_daily_loss_pct):
            if not state.entries_halted():
                logger.warning("Daily loss cutoff reached | start=%.2f current=%.2f", start_equity, equity)
                state.halt_entries()
                state.save()
                notifier.send("🛑 Daily loss cutoff reached")

        if in_no_trade_zone(dt, s.no_trade_first_minutes, s.no_trade_last_minutes):
            logger.info("No-trade time window active")
            return

        refresh_news(False)

        positions = executor.get_positions_map()
        has_position = sym in positions
        current_close = float(frames[sym].iloc[-1]["close"]) if len(frames[sym]) else None
        state.on_new_bar(sym, has_position, current_close)
        ss = state.get_symbol(sym)
        news_score = news_cache.get(sym).bias_score if news_cache.get(sym) else 0

        sig = strategy.evaluate(
            sym, frames[sym], frames[s.benchmark_symbol], frames[s.second_benchmark_symbol],
            news_score=news_score, has_position=has_position, held_bars=int(ss.get("held_bars", 0)),
            entry_price=ss.get("last_entry_price"), max_close_since_entry=ss.get("max_close_since_entry"),
            partial_taken=bool(ss.get("partial_taken", False)),
        )
        LAST_SCORE.labels(symbol=sym).set(sig.score)
        logger.info("Signal | %s | action=%s | score=%s | conf=%s | size_mult=%.2f", sym, sig.action, sig.score, sig.confidence, sig.size_multiplier)

        assessment = news_cache.get(sym)
        news_note = []
        if s.enable_news_filter and assessment and sig.action == "BUY":
            if assessment.bias_score <= s.negative_news_block_score:
                logger.info("Blocked by negative news | %s | score=%s", sym, assessment.bias_score)
                if can_alert(sym + "_BLOCK", assessment.bias_score):
                    notifier.send(f"⛔ BUY BLOCKED BY NEWS — {sym}\nNews score: {assessment.bias_score}")
                return
            if s.require_positive_news_for_buy and assessment.bias_score < s.positive_news_bonus_score:
                logger.info("Buy skipped | %s | positive-news threshold not met", sym)
                return
            if assessment.bias_score >= s.positive_news_bonus_score:
                news_note.append(f"Supportive news/SEC score {assessment.bias_score}")

        if s.enable_news_alpha_alerts and assessment and assessment.bias_score >= s.news_alpha_min_score and (sig.volume_ratio or 1.0) >= s.volume_confirm_ratio and sig.score >= 4:
            fp = f"{assessment.bias_score}:{int((sig.volume_ratio or 1.0) * 100)}:{sig.score}"
            if can_alert(sym + "_ALPHA", fp):
                logger.info("News alpha alert | %s", sym)
                msg = [
                    f"📰 NEWS ALPHA ALERT — {sym}",
                    f"News/SEC score: {assessment.bias_score}",
                    f"Volume ratio: {(sig.volume_ratio or 1.0):.2f}x",
                    f"Technical score: {sig.score}",
                    f"Confidence: {sig.confidence}/5",
                ]
                if assessment.sec_hits:
                    msg.append("SEC findings:")
                    for line in assessment.sec_hits[:2]:
                        msg.append(f"- {line}")
                notifier.send("\n".join(msg))

        if sig.action == "BUY":
            if sig.confidence < 2 or sig.size_multiplier <= 0:
                logger.info("Buy skipped | %s | confidence too low", sym)
                return
            if int(ss.get("cooldown_bars_left", 0)) > 0 or state.daily_trades() >= s.max_trades_per_day or state.entries_halted() or len(positions) >= s.max_open_positions or state.loss_streak() >= s.max_loss_streak:
                logger.info("Buy skipped | %s | risk gate active", sym)
                return

        if sig.action == "SELL" and has_position and int(ss.get("held_bars", 0)) < s.min_hold_bars and sig.score > -9:
            logger.info("Sell skipped | %s | min hold bars active", sym)
            return

        if sig.action in {"BUY", "SELL", "TRIM"} and can_alert(sym + "_" + sig.action, sig.score):
            SIGNALS.labels(symbol=sym, action=sig.action).inc()
            close = float(sig.close or 0.0)
            msg = [
                f"📡 {sym} {sig.action}",
                f"Price: ${close:,.2f}",
                f"Score: {sig.score}",
                f"Confidence: {sig.confidence}/5",
                f"Size multiplier: {sig.size_multiplier:.2f}x",
                f"Volume ratio: {(sig.volume_ratio or 1.0):.2f}x",
                "Reasons:",
            ]
            for r in sig.reasons[:8]:
                msg.append(f"- {r}")
            if news_note:
                msg += ["News context:"] + news_note

            if sig.action == "BUY":
                base_qty = compute_position_size(equity, s.risk_per_trade, close, sig.stop_price, s.max_position_pct)
                qty = int(base_qty * sig.size_multiplier)
                msg.append(f"Base quantity: {base_qty}")
                msg.append(f"Adjusted quantity: {qty}")
                logger.info("Buy decision | %s | base_qty=%s | adj_qty=%s | stop=%.2f", sym, base_qty, qty, float(sig.stop_price or 0))
                if qty > 0:
                    try:
                        order = executor.market_buy(sym, qty)
                        state.set_entry(sym, close, qty)
                        state.inc_daily_trades()
                        state.save()
                        journal.log_trade(sym, "BUY", qty, close, None, None, None, equity, buying_power, "; ".join((sig.reasons + news_note)[:4]))
                        logger.info("Buy submitted | %s | qty=%s | order_id=%s", sym, qty, getattr(order, "id", "unknown"))
                        msg += [f"Order submitted: BUY {qty} {sym}", f"Order id: {getattr(order, 'id', 'unknown')}"]
                    except Exception as e:
                        logger.exception("Buy failed | %s", sym)
                        msg.append(f"Execution failed: {e}")

            elif sig.action == "TRIM" and has_position and s.allow_partial_profit:
                try:
                    pos = positions[sym]
                    qty = max(1, int(float(pos.qty)) // 2)
                    avg = float(pos.avg_entry_price)
                    pl = (close - avg) * qty
                    plpct = ((close - avg) / avg) * 100 if avg > 0 else 0.0
                    order = executor.market_sell(sym, qty)
                    state.mark_partial(sym)
                    state.inc_daily_trades()
                    state.save()
                    journal.log_trade(sym, "TRIM", qty, close, avg, pl, plpct, equity, buying_power, "; ".join(sig.reasons[:4]))
                    logger.info("Trim submitted | %s | qty=%s | pnl=%.2f", sym, qty, pl)
                    msg += [f"Partial sell: {qty} shares", f"Estimated P/L: ${pl:,.2f} ({plpct:.2f}%)", f"Order id: {getattr(order, 'id', 'unknown')}"]
                except Exception as e:
                    logger.exception("Trim failed | %s", sym)
                    msg.append(f"Execution failed: {e}")

            elif sig.action == "SELL" and has_position:
                try:
                    pos = positions[sym]
                    qty = int(float(pos.qty))
                    avg = float(pos.avg_entry_price)
                    pl = (close - avg) * qty
                    plpct = ((close - avg) / avg) * 100 if avg > 0 else 0.0
                    order = executor.market_sell(sym, qty)
                    state.inc_daily_trades()
                    state.record_closed_trade(pl)
                    state.clear_entry(sym)
                    state.start_cooldown(sym, s.cooldown_bars)
                    state.save()
                    journal.log_trade(sym, "SELL", qty, close, avg, pl, plpct, equity, buying_power, "; ".join(sig.reasons[:4]))
                    logger.info("Sell submitted | %s | qty=%s | pnl=%.2f", sym, qty, pl)
                    msg += [f"Shares: {qty}", f"Estimated P/L: ${pl:,.2f} ({plpct:.2f}%)", f"Order id: {getattr(order, 'id', 'unknown')}"]
                except Exception as e:
                    logger.exception("Sell failed | %s", sym)
                    msg.append(f"Execution failed: {e}")

            notifier.send("\n".join(msg))

    def heartbeat():
        while True:
            time.sleep(s.heartbeat_seconds)
            refresh_news(False)
            age = time.time() - rt["last_bar_epoch"]
            rt["hb_count"] += 1
            logger.info("Heartbeat | last_bar_age=%ss | bars_seen=%s", int(age), rt["bars_seen"])

            market_open = is_regular_market_hours(now_et())

            if not market_open:
                if s.smart_heartbeat_alerts and s.send_market_closed_alert and not rt["closed_sent"]:
                    try:
                        notifier.send("🌙 Market closed\nBot alive, waiting for regular hours.")
                        rt["closed_sent"] = True
                    except Exception:
                        pass
                continue
            rt["closed_sent"] = False

            if age > s.stale_data_seconds:
                if s.smart_heartbeat_alerts and not rt["stale_sent"]:
                    try:
                        notifier.send(f"⚠️ Stream stale\nNo fresh bars for {int(age)}s\nLast bar: {rt['last_bar_ts']}")
                    except Exception:
                        pass
                    rt["stale_sent"] = True
                    rt["recovery_sent"] = False
                logger.warning("Stream stale | exiting for restart")
                os._exit(1)

            if s.smart_heartbeat_alerts and s.heartbeat_summary_every_n > 0 and rt["hb_count"] % s.heartbeat_summary_every_n == 0:
                try:
                    notifier.send(
                        f"💓 Bot alive\n"
                        f"Last bar age: {int(age)}s\n"
                        f"Bars seen: {rt['bars_seen']}\n"
                        f"Open market: yes"
                    )
                except Exception:
                    pass

    refresh_news(True)
    threading.Thread(target=heartbeat, daemon=True).start()
    for sym in symbols:
        provider.stream.subscribe_bars(handle_bar, sym)

    logger.info("Starting Alpaca realtime stream...")
    provider.stream.run()

if __name__ == "__main__":
    main()
