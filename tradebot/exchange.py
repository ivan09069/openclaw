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
  ex.active_exchange                              -> str  (paper only)
  await ex.close()
"""

import asyncio
import ccxt.async_support as ccxt
from config import CFG
import logger

_RETRY_DELAYS = (1, 2, 4)  # seconds between attempts 1→2, 2→3, 3→fail

# Paper mode: try these exchanges in order until one responds.
# All support BTC/USD, ETH/USD public OHLCV without auth.
_PAPER_FALLBACKS = ["kraken", "coinbase", "bitstamp"]


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


def _build_aiohttp_session():
    """
    Return an aiohttp ClientSession that uses the threaded (system) DNS
    resolver instead of aiodns/c-ares.

    On Android/Termux, aiodns can fail with "Could not contact DNS servers"
    because c-ares doesn't respect the Android DNS stack.  ThreadedResolver
    delegates to the OS getaddrinfo(), which always works.

    ccxt respects the 'session' key in its config dict and will NOT close
    an externally-supplied session when exchange.close() is called
    (own_session=False), so we manage its lifetime ourselves.
    """
    import aiohttp
    try:
        resolver  = aiohttp.resolver.ThreadedResolver()
        connector = aiohttp.TCPConnector(resolver=resolver)
        session   = aiohttp.ClientSession(connector=connector)
        logger.info("DNS: using ThreadedResolver (system getaddrinfo)")
        return session
    except Exception as e:
        # If something goes wrong building the custom session, log and
        # return None — ccxt will create its own session as normal.
        logger.warn("DNS: ThreadedResolver setup failed, using ccxt default", err=str(e))
        return None


def _make_ccxt(exchange_id: str, session=None):
    """Instantiate a ccxt async exchange, optionally injecting an aiohttp session."""
    cls    = getattr(ccxt, exchange_id)
    params = {"enableRateLimit": True}
    if session is not None:
        params["session"] = session
    return cls(params)


class PaperExchange:
    """
    Real public market data + simulated fills.

    readiness_check() does two things:
      1. Creates an aiohttp session with ThreadedResolver (avoids aiodns on Termux).
      2. Tries CFG.exchange first, then _PAPER_FALLBACKS in order, using the
         first one that successfully returns candle data.
    All subsequent fetch calls use the selected exchange + session.
    """

    def __init__(self):
        self._ex             = _make_ccxt(CFG.exchange)
        self._session        = None   # set in readiness_check
        self.active_exchange = CFG.exchange
        self.equity          = CFG.capital
        self._order_counter  = 0

    async def readiness_check(self) -> tuple[bool, str]:
        """
        Try CFG.exchange, then fallbacks.
        Injects a ThreadedResolver aiohttp session into the selected instance.
        """
        session = _build_aiohttp_session()
        self._session = session  # may be None if build failed

        # Candidate list: configured exchange first, then the rest of
        # _PAPER_FALLBACKS that aren't already first.
        candidates = [CFG.exchange] + [
            x for x in _PAPER_FALLBACKS if x != CFG.exchange
        ]

        # Use BTC/USD as the probe symbol — available on all three fallbacks.
        probe_symbol = "BTC/USD"
        probe_tf     = CFG.timeframe

        failures: list[str] = []

        for exchange_id in candidates:
            # (Re)create instance, injecting session each time so it uses
            # our ThreadedResolver even on the first candidate.
            try:
                await self._ex.close()
            except Exception:
                pass
            self._ex = _make_ccxt(exchange_id, session=session)

            try:
                data = await self._ex.fetch_ohlcv(probe_symbol, probe_tf, limit=1)
                if not data:
                    reason = f"{exchange_id}: fetch returned empty list"
                    logger.warn(f"paper readiness: {reason}")
                    failures.append(reason)
                    continue

                # Success
                self.active_exchange = exchange_id
                if exchange_id != CFG.exchange:
                    logger.info(
                        f"paper: selected fallback exchange '{exchange_id}' "
                        f"(configured '{CFG.exchange}' failed: "
                        f"{'; '.join(failures)})"
                    )
                else:
                    logger.info(f"paper: exchange '{exchange_id}' ready")
                return True, f"ok (exchange={exchange_id})"

            except Exception as e:
                reason = f"{exchange_id}: {str(e)[:100]}"
                logger.warn(f"paper readiness probe failed — {reason}")
                failures.append(reason)

        # All candidates exhausted
        if session:
            try:
                await session.close()
            except Exception:
                pass
            self._session = None
        return False, f"all exchange candidates failed: {failures}"

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list:
        try:
            return await _with_retry(
                lambda: self._ex.fetch_ohlcv(symbol, timeframe, limit=limit),
                f"fetch_ohlcv({symbol}@{self.active_exchange})",
            )
        except Exception as e:
            logger.error("fetch_ohlcv failed after retries", symbol=symbol, err=str(e)[:120])
            return []  # fail closed: no data → no trade

    async def fetch_ticker(self, symbol: str) -> dict:
        try:
            t = await _with_retry(
                lambda: self._ex.fetch_ticker(symbol),
                f"fetch_ticker({symbol}@{self.active_exchange})",
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
        # Close our manually-managed aiohttp session (ccxt won't, own_session=False)
        if self._session is not None and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass


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
