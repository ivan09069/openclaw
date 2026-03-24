"""report.py — Quick P&L report from the DB. Run anytime.

Usage: python report.py
"""
import asyncio
import aiosqlite
from config import CFG


async def main():
    async with aiosqlite.connect(CFG.db_path) as conn:
        conn.row_factory = aiosqlite.Row

        print("\n=== OPEN POSITIONS ===")
        rows = await (await conn.execute(
            "SELECT id,symbol,side,entry_price,size,sl,tp,opened_at FROM positions WHERE status='open'"
        )).fetchall()
        if rows:
            for r in rows:
                r = dict(r)
                print(f"  #{r['id']} {r['symbol']:12} {r['side']:5} entry={r['entry_price']:.4f} "
                      f"size={r['size']:.6f} sl={r['sl']:.4f} tp={r['tp']:.4f} "
                      f"opened={r['opened_at'][:19]}")
        else:
            print("  (none)")

        print("\n=== CLOSED TRADES ===")
        rows = await (await conn.execute(
            """SELECT id,symbol,side,entry_price,close_price,pnl,close_reason,closed_at
               FROM positions WHERE status='closed' ORDER BY closed_at DESC LIMIT 20"""
        )).fetchall()
        total_pnl = 0.0
        wins = losses = 0
        for r in rows:
            r = dict(r)
            pnl = r["pnl"] or 0.0
            total_pnl += pnl
            flag = "✅" if pnl >= 0 else "❌"
            if pnl >= 0: wins += 1
            else: losses += 1
            print(f"  {flag} #{r['id']} {r['symbol']:12} {r['side']:5} "
                  f"entry={r['entry_price']:.4f} → {r['close_price']:.4f} "
                  f"pnl={pnl:+.4f} ({r['close_reason']}) {r['closed_at'][:19]}")

        print(f"\n  Total PnL: {total_pnl:+.4f} | Wins: {wins} | Losses: {losses} | "
              f"Win rate: {wins/(wins+losses)*100:.1f}%" if (wins+losses) else "  No closed trades yet")

        print("\n=== DAILY STATS ===")
        rows = await (await conn.execute(
            "SELECT date,realized_pnl,trades_won,trades_lost,halted FROM daily_stats ORDER BY date DESC LIMIT 7"
        )).fetchall()
        for r in rows:
            r = dict(r)
            halt_flag = " [HALTED]" if r["halted"] else ""
            total = r["trades_won"] + r["trades_lost"]
            wr = f"{r['trades_won']/total*100:.0f}%" if total else "—"
            print(f"  {r['date']}  pnl={r['realized_pnl']:+.4f}  "
                  f"{r['trades_won']}W/{r['trades_lost']}L  wr={wr}{halt_flag}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
