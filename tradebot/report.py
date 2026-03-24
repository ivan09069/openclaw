"""report.py — Paper-trade analytics

Usage:
  python report.py                   # all closed trades
  python report.py --symbol BTC/USD  # single symbol
  python report.py --since 2024-01-01

Reads from SQLite only (no network).
"""

import asyncio
import argparse
import sys
import math
from datetime import datetime

# Bootstrap DB path before importing config (config reads .env)
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import db
from config import CFG


# ── Metrics ───────────────────────────────────────────────────────────────────

def _safe(v, fallback=0.0):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return fallback
    return v


def compute_metrics(trades: list) -> dict:
    if not trades:
        return {}

    pnls   = [_safe(t.get("pnl", 0)) for t in trades]
    rs     = [_safe(t.get("r_multiple", 0)) for t in trades]
    fees   = [_safe(t.get("fees", 0)) for t in trades]
    durs   = [_safe(t.get("duration_s", 0)) for t in trades]

    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_pnl   = sum(pnls)
    total_fees  = sum(fees)
    net_pnl     = total_pnl - total_fees
    win_rate    = len(wins) / len(pnls) if pnls else 0
    avg_win     = sum(wins)   / len(wins)   if wins   else 0
    avg_loss    = sum(losses) / len(losses) if losses else 0
    avg_r       = sum(rs)     / len(rs)     if rs     else 0

    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    loss_rate  = 1 - win_rate
    expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)

    # Max drawdown (running equity curve from CFG.capital)
    equity  = CFG.capital
    peak    = equity
    max_dd  = 0.0
    for p in pnls:
        equity += p
        peak    = max(peak, equity)
        dd      = (peak - equity) / peak if peak > 0 else 0
        max_dd  = max(max_dd, dd)

    avg_duration_m = (sum(durs) / len(durs) / 60) if durs else 0

    return {
        "total_trades":  len(trades),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate":      win_rate,
        "avg_win_usd":   avg_win,
        "avg_loss_usd":  avg_loss,
        "expectancy":    expectancy,
        "profit_factor": profit_factor,
        "gross_profit":  gross_profit,
        "gross_loss":    gross_loss,
        "total_pnl":     total_pnl,
        "total_fees":    total_fees,
        "net_pnl":       net_pnl,
        "avg_r":         avg_r,
        "max_drawdown":  max_dd,
        "avg_duration_m": avg_duration_m,
    }


def _bar(val: float, max_val: float, width: int = 20, char: str = "█") -> str:
    if max_val <= 0:
        return ""
    filled = int(width * min(val, max_val) / max_val)
    return char * filled + "░" * (width - filled)


def print_report(trades: list, title: str = "All trades") -> None:
    m = compute_metrics(trades)
    if not m:
        print(f"\n  ⚠  No closed trades found for: {title}\n")
        return

    pf = m["profit_factor"]
    pf_str = f"{pf:.2f}" if pf != float("inf") else "∞"

    w  = 52
    hr = "─" * w

    print()
    print(f"╔{'═'*w}╗")
    print(f"║  📊 Paper Trade Report — {title:<{w-28}}║")
    print(f"╠{hr}╣")
    print(f"║  Total trades      : {m['total_trades']:<30}║")
    print(f"║  Wins / Losses     : {m['wins']} / {m['losses']:<27}║")
    print(f"║  Win rate          : {m['win_rate']:.1%}  {_bar(m['win_rate'], 1.0):<20}║")
    print(f"╠{hr}╣")
    print(f"║  Avg win           : ${m['avg_win_usd']:>+.2f}{'':>26}║")
    print(f"║  Avg loss          : ${m['avg_loss_usd']:>+.2f}{'':>26}║")
    print(f"║  Expectancy        : ${m['expectancy']:>+.4f} per trade{'':>16}║")
    print(f"║  Profit factor     : {pf_str:<30}║")
    print(f"╠{hr}╣")
    print(f"║  Gross profit      : ${m['gross_profit']:>+.2f}{'':>26}║")
    print(f"║  Gross loss        : ${-m['gross_loss']:>+.2f}{'':>26}║")
    print(f"║  Total fees        : ${m['total_fees']:>.2f}{'':>27}║")
    print(f"║  Total PnL (gross) : ${m['total_pnl']:>+.2f}{'':>26}║")
    print(f"║  Net PnL (−fees)   : ${m['net_pnl']:>+.2f}{'':>26}║")
    print(f"╠{hr}╣")
    print(f"║  Avg R multiple    : {m['avg_r']:>+.2f}R{'':>28}║")
    print(f"║  Max drawdown      : {m['max_drawdown']:.2%}{'':>30}║")
    print(f"║  Avg trade duration: {m['avg_duration_m']:.1f} min{'':>28}║")
    print(f"╚{'═'*w}╝")


def print_symbol_breakdown(trades: list) -> None:
    from collections import defaultdict
    by_sym: dict = defaultdict(list)
    for t in trades:
        by_sym[t["symbol"]].append(t)

    if len(by_sym) <= 1:
        return  # already shown in main report

    print(f"\n{'─'*54}")
    print(f"  Per-symbol breakdown")
    print(f"{'─'*54}")
    print(f"  {'Symbol':<12}  {'N':>4}  {'WR':>6}  {'NetPnL':>10}  {'AvgR':>6}")
    print(f"{'─'*54}")
    for sym, sym_trades in sorted(by_sym.items()):
        m = compute_metrics(sym_trades)
        pf_str = f"{m['profit_factor']:.2f}" if m["profit_factor"] != float("inf") else "∞"
        print(
            f"  {sym:<12}  {m['total_trades']:>4}  "
            f"{m['win_rate']:>5.1%}  "
            f"${m['net_pnl']:>+9.2f}  "
            f"{m['avg_r']:>+5.2f}R"
        )
    print(f"{'─'*54}")


def print_trade_log(trades: list, limit: int = 20) -> None:
    if not trades:
        return
    print(f"\n  Last {min(limit, len(trades))} closed trades:")
    print(f"  {'#':>4}  {'Symbol':<10}  {'Side':<5}  {'Entry':>10}  "
          f"{'Exit':>10}  {'PnL':>8}  {'R':>5}  {'Dur':>7}  Reason")
    print(f"  {'─'*90}")
    for t in trades[-limit:]:
        dur_m  = _safe(t.get("duration_s", 0)) / 60
        pnl    = _safe(t.get("pnl", 0))
        r      = _safe(t.get("r_multiple", 0))
        entry  = _safe(t.get("entry_price", 0))
        exit_p = _safe(t.get("close_price", 0))
        print(
            f"  {t['id']:>4}  {t['symbol']:<10}  {t['side']:<5}  "
            f"{entry:>10.2f}  {exit_p:>10.2f}  "
            f"${pnl:>+7.2f}  {r:>+4.2f}R  {dur_m:>5.1f}m  "
            f"{t.get('close_reason','')}"
        )


async def run(symbol: str = None, since: str = None, verbose: bool = False) -> None:
    await db.init_db()
    trades = await db.get_journal(symbol=symbol)

    if since:
        trades = [t for t in trades if t.get("closed_at", "") >= since]

    title = symbol or "all symbols"
    if since:
        title += f" since {since}"

    print_report(trades, title=title)
    print_symbol_breakdown(trades)

    if verbose:
        print_trade_log(trades)

    total = await db.get_closed_count()
    needed = CFG.min_paper_trades_for_live
    print(f"\n  Closed trades total: {total}  (need {needed} to unlock live mode)")
    if total >= needed:
        print(f"  ✅ Live-mode trade count gate: PASSED")
    else:
        print(f"  ⏳ Live-mode gate: need {needed - total} more trade(s)")
    print()


def main():
    parser = argparse.ArgumentParser(description="Paper trade analytics report")
    parser.add_argument("--symbol", default=None, help="Filter by symbol, e.g. BTC/USD")
    parser.add_argument("--since",  default=None, help="Filter by closed_at date, e.g. 2024-01-01")
    parser.add_argument("--verbose", action="store_true", help="Print individual trade log")
    args = parser.parse_args()
    asyncio.run(run(symbol=args.symbol, since=args.since, verbose=args.verbose))


if __name__ == "__main__":
    main()
