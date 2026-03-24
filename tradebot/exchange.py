"""exchange.py — Unified interface for paper / testnet / live

Paper mode: no network calls for orders. Prices come from real public
market data (no API key needed). Orders are simulated at market price.

Testnet: Binance testnet (API key required, fake money).

Live: real exchange via ccxt.

Public interface:
  await ex.fetch_ohlcv(symbol, timeframe, limit) -> list
  await ex.fetch_ticker(symbol) -> {"last": float, "bid": float, "ask": float}
  await ex.place_order(symbol, side, size, price) -> {"id": str, "price": float, "filled": float}
  ex.equity -> float (current equity / paper balance)
  await ex.close() -> None
"""

import asyncio
import ccxt.async_support as ccxt
from config import CFG
import logger


class PaperExchange:
    """
    Wraps a real (no-auth) exchange for market data.
    All order placements are simulated instantly at last price.
    """
    def __init__(self):
        cls = getattr(ccxt, CFG.exchange)
        self._ex = cls({"enableRateLimit": True})
        self.equity = CFG.capital
        self._order_counter = 0

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list:
        for attempt in range(3):
            try:
                return await self._ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            except Exception as e:
                logger.warn(f"fetch_ohlcv attempt {attempt+1} failed", symbol=symbol, err=str(e))
                await asyncio.sleep(2 ** attempt)
        return []

    async def fetch_ticker(self, symbol: str) -> dict:
        for attempt in range(3):
            try:
                t = await self._ex.fetch_ticker(symbol)
                return {"last": t["last"], "bid": t.get("bid", t["last"]),
                        "ask": t.get("ask", t["last"])}
            except Exception as e:
                logger.warn(f"fetch_ticker attempt {attempt+1} failed", symbol=symbol, err=str(e))
                await asyncio.sleep(2 ** attempt)
        return {"last": 0.0, "bid": 0.0, "ask": 0.0}

    async def place_order(self, symbol: str, side: str, size: float, price: float) -> dict:
        """Simulate a market order fill at given price."""
        self._order_counter += 1
        oid = f"PAPER-{self._order_counter}"
        notional = size * price
        logger.trade("PAPER_FILL", symbol=symbol, side=side,
                     size=round(size, 6), price=price, notional=round(notional, 2), id=oid)
        return {"id": oid, "price": price, "filled": size}

    async def close(self) -> None:
        await self._ex.close()


class LiveExchange:
    """
    Real exchange. Testnet = same class, sandboxMode=True.
    Places actual market orders. Use only after paper validation.
    """
    def __init__(self):
        cls = getattr(ccxt, CFG.exchange)
        params = {
            "apiKey": CFG.api_key,
            "secret": CFG.api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        self._ex = cls(params)
        if CFG.mode == "testnet":
            self._ex.set_sandbox_mode(True)
        self._equity_cache: float | None = None

    @property
    def equity(self) -> float:
        return self._equity_cache or CFG.capital

    async def _refresh_equity(self) -> None:
        try:
            bal = await self._ex.fetch_balance()
            usdt = bal.get("USDT", {})
            self._equity_cache = float(usdt.get("free", CFG.capital))
        except Exception as e:
            logger.warn("equity refresh failed", err=str(e))

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list:
        for attempt in range(3):
            try:
                return await self._ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            except Exception as e:
                logger.warn(f"fetch_ohlcv attempt {attempt+1} failed", symbol=symbol, err=str(e))
                await asyncio.sleep(2 ** attempt)
        return []

    async def fetch_ticker(self, symbol: str) -> dict:
        for attempt in range(3):
            try:
                t = await self._ex.fetch_ticker(symbol)
                return {"last": t["last"], "bid": t.get("bid", t["last"]),
                        "ask": t.get("ask", t["last"])}
            except Exception as e:
                logger.warn(f"fetch_ticker attempt {attempt+1} failed", symbol=symbol, err=str(e))
                await asyncio.sleep(2 ** attempt)
        return {"last": 0.0, "bid": 0.0, "ask": 0.0}

    async def place_order(self, symbol: str, side: str, size: float, price: float) -> dict:
        await self._refresh_equity()
        for attempt in range(3):
            try:
                order = await self._ex.create_market_order(symbol, side, size)
                filled = float(order.get("filled", size))
                avg    = float(order.get("average") or order.get("price") or price)
                logger.trade("LIVE_FILL", symbol=symbol, side=side,
                             size=filled, price=avg, id=order["id"])
                return {"id": order["id"], "price": avg, "filled": filled}
            except Exception as e:
                logger.error(f"place_order attempt {attempt+1} failed",
                             symbol=symbol, side=side, err=str(e))
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"Order failed after 3 attempts: {symbol} {side} {size}")

    async def close(self) -> None:
        await self._ex.close()


def build_exchange():
    if CFG.mode == "paper":
        logger.info("Exchange: PAPER mode (simulated orders, real market data)")
        return PaperExchange()
    elif CFG.mode == "testnet":
        logger.info("Exchange: TESTNET mode (Binance sandbox)")
        return LiveExchange()
    else:
        logger.info("Exchange: LIVE mode — real money, real orders")
        return LiveExchange()
