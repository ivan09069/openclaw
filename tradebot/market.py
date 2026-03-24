"""market.py — Exchange connector (paper/testnet/live)"""
import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta
from config import CFG
import logger

_exchange = None


def _build_exchange():
    params = {"enableRateLimit": True}
    if CFG.api_key:
        params["apiKey"] = CFG.api_key
        params["secret"] = CFG.api_secret
    ex = getattr(ccxt, CFG.exchange)(params)
    if CFG.mode == "testnet":
        ex.set_sandbox_mode(True)
    return ex


def get_exchange():
    global _exchange
    if _exchange is None:
        _exchange = _build_exchange()
    return _exchange


async def fetch_ohlcv(symbol: str) -> pd.DataFrame:
    """Fetch OHLCV candles and compute indicators."""
    ex = get_exchange()
    raw = await ex.fetch_ohlcv(symbol, timeframe=CFG.timeframe, limit=CFG.ohlcv_limit)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df.set_index("ts", inplace=True)

    # Indicators
    df[f"ema{CFG.ema_fast}"] = ta.ema(df["close"], length=CFG.ema_fast)
    df[f"ema{CFG.ema_slow}"] = ta.ema(df["close"], length=CFG.ema_slow)
    df["rsi"]               = ta.rsi(df["close"], length=CFG.rsi_period)
    atr_col = f"ATRr_{CFG.atr_period}"
    df["atr"]               = ta.atr(df["high"], df["low"], df["close"], length=CFG.atr_period)
    return df.dropna()


async def fetch_price(symbol: str) -> float:
    ex = get_exchange()
    ticker = await ex.fetch_ticker(symbol)
    return float(ticker["last"])


async def close_exchange():
    global _exchange
    if _exchange:
        await _exchange.close()
        _exchange = None
