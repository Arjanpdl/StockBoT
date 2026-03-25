import pandas as pd

def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()

def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    ag = g.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    al = l.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = ag / al.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)

def macd(s: pd.Series):
    f = ema(s, 12)
    sl = ema(s, 26)
    line = f - sl
    sig = ema(line, 9)
    hist = line - sig
    return line, sig, hist

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(period).mean()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    o = df.copy()
    o["ema20"] = ema(o["close"], 20)
    o["ema50"] = ema(o["close"], 50)
    o["ema200"] = ema(o["close"], 200)
    o["rsi14"] = rsi(o["close"], 14)
    o["macd"], o["macd_signal"], o["macd_hist"] = macd(o["close"])
    o["vol20"] = o["volume"].rolling(20).mean()
    o["atr14"] = atr(o, 14)
    o["high20"] = o["high"].rolling(20).max()
    o["low20"] = o["low"].rolling(20).min()
    o["ema20_slope"] = o["ema20"] - o["ema20"].shift(3)
    o["extension_pct"] = (o["close"] - o["ema20"]) / o["ema20"]
    o["vol_ratio"] = o["volume"] / o["vol20"]
    return o
