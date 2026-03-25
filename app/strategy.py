from dataclasses import dataclass
import pandas as pd

@dataclass
class Signal:
    symbol: str
    action: str
    score: int
    reasons: list[str]
    stop_price: float | None = None
    close: float | None = None
    risk_per_share: float | None = None
    partial_take: bool = False
    volume_ratio: float | None = None
    dollar_volume: float | None = None
    gap_pct: float | None = None
    confidence: int = 0
    size_multiplier: float = 0.0

class FinalOptimizedStrategy:
    def __init__(
        self,
        atr_multiplier=2.5,
        min_stop_pct=0.02,
        overextension_pct=0.03,
        volume_confirm_ratio=1.3,
        high_conviction_volume_ratio=2.0,
        min_dollar_volume=5_000_000,
        max_gap_pct=0.08,
        require_relative_strength=False,
        time_stop_bars=30,
        time_stop_min_r=0.3,
    ):
        self.atr_multiplier = atr_multiplier
        self.min_stop_pct = min_stop_pct
        self.overextension_pct = overextension_pct
        self.volume_confirm_ratio = volume_confirm_ratio
        self.high_conviction_volume_ratio = high_conviction_volume_ratio
        self.min_dollar_volume = min_dollar_volume
        self.max_gap_pct = max_gap_pct
        self.require_relative_strength = require_relative_strength
        self.time_stop_bars = time_stop_bars
        self.time_stop_min_r = time_stop_min_r

    def regime_ok(self, b1, b2) -> bool:
        if len(b1) < 80 or len(b2) < 80:
            return False
        def good(df):
            x = df.iloc[-1]
            return bool(
                x["close"] > x["ema50"] > x["ema200"]
                and x["ema20"] > x["ema50"]
                and x["ema20_slope"] > 0
            )
        return good(b1) and good(b2)

    def compute_stop(self, close: float, atr14: float | None) -> float:
        atr_part = self.atr_multiplier * atr14 if atr14 is not None and pd.notna(atr14) and atr14 > 0 else 0.0
        return float(close - max(close * self.min_stop_pct, atr_part))

    def confidence_score(self, score: int, volume_ratio: float, news_score: int, regime_ok: bool) -> int:
        c = 0
        if score >= 6:
            c += 2
        if score >= 8:
            c += 1
        if volume_ratio >= 1.5:
            c += 1
        if volume_ratio >= 2.0:
            c += 1
        if news_score >= 15:
            c += 1
        if news_score >= 25:
            c += 1
        if regime_ok:
            c += 1
        return int(min(c, 5))

    def size_multiplier(self, conf: int) -> float:
        return {0: 0.0, 1: 0.0, 2: 0.5, 3: 1.0, 4: 1.25, 5: 1.5}.get(conf, 0.0)

    def evaluate(
        self,
        symbol,
        df,
        bench1,
        bench2,
        news_score=0,
        has_position=False,
        held_bars=0,
        entry_price=None,
        max_close_since_entry=None,
        partial_taken=False,
    ) -> Signal:
        if len(df) < 80 or len(bench1) < 80 or len(bench2) < 80:
            return Signal(symbol, "WAIT", 0, ["Not enough bars yet"])

        x = df.iloc[-1]
        p = df.iloc[-2]
        ph = df["high20"].shift(1).iloc[-1]
        pl = df["low20"].shift(1).iloc[-1]
        score = 0
        reasons = []
        vol_ratio = float(x["vol_ratio"]) if pd.notna(x["vol_ratio"]) else 1.0
        dollar_volume = float(x["close"]) * float(x["volume"])
        gap_pct = (float(x["open"]) / float(p["close"]) - 1.0) if float(p["close"]) > 0 else 0.0
        stock_ret20 = (float(x["close"]) / float(df["close"].iloc[-20]) - 1.0) if len(df) >= 20 and float(df["close"].iloc[-20]) > 0 else 0.0
        spy_ret20 = (float(bench1["close"].iloc[-1]) / float(bench1["close"].iloc[-20]) - 1.0) if len(bench1) >= 20 and float(bench1["close"].iloc[-20]) > 0 else 0.0
        qqq_ret20 = (float(bench2["close"].iloc[-1]) / float(bench2["close"].iloc[-20]) - 1.0) if len(bench2) >= 20 and float(bench2["close"].iloc[-20]) > 0 else 0.0
        regime = self.regime_ok(bench1, bench2)

        if x["close"] > x["ema20"] > x["ema50"] > x["ema200"] and x["ema20_slope"] > 0:
            score += 4
            reasons.append("Strong bullish trend")
        elif x["close"] < x["ema20"] < x["ema50"] < x["ema200"]:
            score -= 4
            reasons.append("Strong bearish trend")
        else:
            reasons.append("Trend mixed")

        if self.require_relative_strength:
            if stock_ret20 > spy_ret20 and stock_ret20 > qqq_ret20:
                score += 2
                reasons.append("Relative strength vs SPY/QQQ")
            else:
                score -= 1
                reasons.append("Relative strength weak")
        else:
            if stock_ret20 > spy_ret20:
                score += 1
                reasons.append("Relative strength positive")

        if 50 <= x["rsi14"] <= 68:
            score += 1
            reasons.append("RSI constructive")
        elif x["rsi14"] < 40:
            score -= 1
            reasons.append("RSI weak")
        elif x["rsi14"] > 78:
            score -= 1
            reasons.append("RSI extended")

        if x["macd_hist"] > 0 and p["macd_hist"] > 0:
            score += 1
            reasons.append("MACD positive 2 bars")
        elif x["macd_hist"] < 0 and p["macd_hist"] < 0:
            score -= 1
            reasons.append("MACD negative 2 bars")

        if dollar_volume < self.min_dollar_volume:
            score -= 2
            reasons.append("Low dollar volume")
        else:
            reasons.append(f"Dollar volume ${dollar_volume:,.0f}")

        if vol_ratio >= self.high_conviction_volume_ratio and x["close"] >= x["open"]:
            score += 3
            reasons.append("High conviction volume surge")
        elif vol_ratio >= self.volume_confirm_ratio and x["close"] >= x["open"]:
            score += 2
            reasons.append("Constructive volume confirmation")
        elif vol_ratio >= 1.0:
            score += 1
            reasons.append("Normal volume support")
        else:
            score -= 1
            reasons.append("Volume weak")

        if gap_pct > self.max_gap_pct:
            score -= 3
            reasons.append("Gap very large")
        elif gap_pct > 0.05:
            score -= 1
            reasons.append("Opening gap elevated")

        breakout = pd.notna(ph) and x["close"] > ph and x["close"] >= x["open"]
        pullback_hold = (
            x["close"] > x["ema20"]
            and x["low"] <= x["ema20"]
            and x["close"] >= x["open"]
            and p["close"] > p["ema20"]
        )
        if breakout:
            score += 1
            reasons.append("Breakout confirmed")
        elif pullback_hold:
            score += 1
            reasons.append("EMA20 pullback hold")

        if pd.notna(x["extension_pct"]) and x["extension_pct"] > self.overextension_pct:
            score -= 2
            reasons.append("Too extended from EMA20")

        if not regime:
            score -= 3
            reasons.append("SPY/QQQ regime failed")

        stop = self.compute_stop(float(x["close"]), float(x["atr14"]) if pd.notna(x["atr14"]) else None)
        risk_per_share = float(x["close"] - stop) if stop is not None else None

        conf = self.confidence_score(score, vol_ratio, news_score, regime)
        size_mult = self.size_multiplier(conf)

        if has_position and entry_price and risk_per_share and risk_per_share > 0:
            initial_risk = max(entry_price - stop, 0.01)
            open_r = (float(x["close"]) - entry_price) / initial_risk

            if held_bars < 3:
                return Signal(symbol, "HOLD", score, reasons + ["Ignoring early noise"], stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)

            if held_bars >= 1 and float(x["close"]) <= stop:
                return Signal(symbol, "SELL", -9, reasons + ["Hard stop breached"], stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)

            if held_bars >= self.time_stop_bars and open_r < self.time_stop_min_r:
                return Signal(symbol, "SELL", score - 1, reasons + ["Time stop"], stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)

            if (not partial_taken) and open_r >= 2.0:
                return Signal(symbol, "TRIM", score, reasons + ["Partial profit at +2R"], stop, float(x["close"]), risk_per_share, True, vol_ratio, dollar_volume, gap_pct, conf, size_mult)

            trail_stop = max(stop, float(x["ema20"])) if open_r >= 2.0 else stop
            if open_r >= 1.0:
                trail_stop = max(trail_stop, entry_price)
            trailing_cut = max_close_since_entry - (1.5 * float(x["atr14"]) if pd.notna(x["atr14"]) else 0) if max_close_since_entry is not None else trail_stop
            if max_close_since_entry is not None and open_r >= 2.0 and float(x["close"]) < max(trail_stop, trailing_cut):
                return Signal(symbol, "SELL", score - 2, reasons + ["Trailing stop triggered"], trail_stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)

        exit_confirm = 0
        if has_position:
            if x["close"] < x["ema20"]:
                exit_confirm += 1
                reasons.append("Below EMA20")
            if x["macd_hist"] < 0 and p["macd_hist"] < 0:
                exit_confirm += 1
            if x["close"] < p["close"]:
                exit_confirm += 1
            if pd.notna(pl) and x["close"] < pl:
                exit_confirm += 2
                reasons.append("Support broken")
            if not regime:
                exit_confirm += 1
            if exit_confirm >= 5 and score <= 0:
                return Signal(symbol, "SELL", score - exit_confirm, reasons, stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)
            return Signal(symbol, "HOLD", score, reasons, stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)

        if score >= 6:
            return Signal(symbol, "BUY", score, reasons, stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)
        return Signal(symbol, "HOLD", score, reasons, stop, float(x["close"]), risk_per_share, False, vol_ratio, dollar_volume, gap_pct, conf, size_mult)
