"""exchange.py — Unified interface for paper / testnet / live

Paper mode:  no auth, real public market data, simulated fills at last price.
Testnet:     ccxt sandboxMode=True, real API flow, fake money.
Live:        real exchange, real money — gated by livecheck.py.

Public interface:
  await ex.fetch_ohlcv(symbol, timeframe, limit)  -> list | []
  await ex.fetch_ticker(symbol)                   -> {"last","bid","ask"} | zeros
  await ex.place_order(symbol, side, size, price) -> {"id","price","filled"}
  await ex.readiness_check()                      -> (ok: bool, reason: str)
  ex.equity                                       -> float
  await ex.close()
"""

import asyncio
import ccxt.async_support as ccxt
from config import CFG
import logger

_RETRY_DELAYS = (1, 2, 4)  # seconds between attempts 1→2, 2→3, 3→fail


async def _with_retry(coro_fn, label: str):
    """
    Run coro_fn() up to 3 times with exponential backoff.
    Returns result or raises on final failure.
    """
    last_exc = None
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        try:
            return await coro_fn()
        except Exception as e:
            last_exc = e
            logger.warn(
                f"{label} attempt {attempt} failed",
                err=str(e)[:120],
            )
            if attempt < len(_RETRY_DELAYS):
                await asyncio.sleep(delay)
    raise last_exc


class PaperExchange:
    """Real public market data + simulated fills."""

    def __init__(self):
        cls = getattr(ccxt, CFG.exchange)
        self._ex = cls({"enableRateLimit": True})
        self.equity = CFG.capital
        self._order_counter = 0

    async def readiness_check(self) -> tuple[bool, str]:
        """Fetch one candle to confirm exchange connectivity."""
        try:
            symbol = CFG.symbols[0]
            data = await self._ex.fetch_ohlcv(symbol, CFG.timeframe, limit=1)
            if not data:
                return False, f"no candle data returned for {symbol}"
            return True, "ok"
        except Exception as e:
            return False, f"exchange connectivity failed: {e}"

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list:
        try:
            return await _with_retry(
                lambda: self._ex.fetch_ohlcv(symbol, timeframe, limit=limit),
                f"fetch_ohlcv({symbol})",
            )
        except Exception as e:
            logger.error("fetch_ohlcv failed after retries", symbol=symbol, err=str(e)[:120])
            return []  # fail closed: no data → no trade

    async def fetch_ticker(self, symbol: str) -> dict:
        try:
            t = await _with_retry(
                lambda: self._ex.fetch_ticker(symbol),
                f"fetch_ticker({symbol})",
            )
            return {
                "last": t["last"],
                "bid":  t.get("bid") or t["last"],
                "ask":  t.get("ask") or t["last"],
            }
        except Exception as e:
            logger.error("fetch_ticker failed after retries", symbol=symbol, err=str(e)[:120])
            return {"last": 0.0, "bid": 0.0, "ask": 0.0}  # fail closed

    async def place_order(self, symbol: str, side: str, size: float, price: float) -> dict:
        self._order_counter += 1
        oid      = f"PAPER-{self._order_counter}"
        notional = size * price
        logger.trade(
            "PAPER_FILL",
            symbol=symbol, side=side,
            size=round(size, 6), price=price,
            notional=round(notional, 2), id=oid,
        )
        return {"id": oid, "price": price, "filled": size}

    async def close(self) -> None:
        await self._ex.close()


class LiveExchange:
    """Authenticated exchange.  Testnet = sandboxMode=True."""

    def __init__(self):
        cls    = getattr(ccxt, CFG.exchange)
        params = {
            "apiKey":          CFG.api_key,
            "secret":          CFG.api_secret,
            "enableRateLimit": True,
            "options":         {"defaultType": "spot"},
        }
        self._ex = cls(params)
        if CFG.mode == "testnet":
            self._ex.set_sandbox_mode(True)
        self._equity_cache: float | None = None

    @property
    def equity(self) -> float:
        return self._equity_cache if self._equity_cache is not None else CFG.capital

    async def readiness_check(self) -> tuple[bool, str]:
        """Verify API keys work and balance is retrievable."""
        try:
            await self._refresh_equity()
            if self._equity_cache is None:
                return False, "balance fetch returned None"
            symbol = CFG.symbols[0]
            data   = await self._ex.fetch_ohlcv(symbol, CFG.timeframe, limit=1)
            if not data:
                return False, f"no candle data for {symbol}"
            return True, f"ok (equity={self._equity_cache:.2f})"
        except Exception as e:
            return False, f"readiness check failed: {e}"

    async def _refresh_equity(self) -> None:
        try:
            bal  = await self._ex.fetch_balance()
            # Support both USDT and USD quote currencies
            for quote in ("USDT", "USD", "BUSD"):
                entry = bal.get(quote, {})
                val   = entry.get("free")
                if val is not None:
                    self._equity_cache = float(val)
                    return
        except Exception as e:
            logger.warn("equity refresh failed", err=str(e)[:120])

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list:
        try:
            return await _with_retry(
                lambda: self._ex.fetch_ohlcv(symbol, timeframe, limit=limit),
                f"fetch_ohlcv({symbol})",
            )
        except Exception as e:
            logger.error("fetch_ohlcv failed after retries", symbol=symbol, err=str(e)[:120])
            return []

    async def fetch_ticker(self, symbol: str) -> dict:
        try:
            t = await _with_retry(
                lambda: self._ex.fetch_ticker(symbol),
                f"fetch_ticker({symbol})",
            )
            return {
                "last": t["last"],
                "bid":  t.get("bid") or t["last"],
                "ask":  t.get("ask") or t["last"],
            }
        except Exception as e:
            logger.error("fetch_ticker failed after retries", symbol=symbol, err=str(e)[:120])
            return {"last": 0.0, "bid": 0.0, "ask": 0.0}

    async def place_order(
        self, symbol: str, side: str, size: float, price: float
    ) -> dict:
        await self._refresh_equity()
        try:
            order  = await _with_retry(
                lambda: self._ex.create_market_order(symbol, side, size),
                f"place_order({symbol},{side})",
            )
            filled = float(order.get("filled", size))
            avg    = float(order.get("average") or order.get("price") or price)
            logger.trade(
                "LIVE_FILL",
                symbol=symbol, side=side,
                size=filled, price=avg, id=order["id"],
            )
            return {"id": order["id"], "price": avg, "filled": filled}
        except Exception as e:
            # Fail closed: surface the error, do NOT silently continue
            logger.error(
                "place_order FAILED — no position opened",
                symbol=symbol, side=side, err=str(e)[:200],
            )
            raise

    async def close(self) -> None:
        await self._ex.close()


def build_exchange():
    if CFG.mode == "paper":
        logger.info("Exchange: PAPER mode (simulated orders, real market data)")
        return PaperExchange()
    elif CFG.mode == "testnet":
        logger.info("Exchange: TESTNET mode")
        return LiveExchange()
    else:
        logger.info("Exchange: LIVE mode — real money, real orders")
        return LiveExchange()
