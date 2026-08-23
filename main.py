"""
Orchestrator: runs the PumpPortal graduation watcher and the X mention
scanner concurrently, and prints a live alert whenever a graduated token
crosses the attention threshold.

    python main.py

Ctrl+C to stop. Everything is also persisted to signals.db (SQLite), so you
can run `python correlate.py` any time to see the full report, even while
this is running or after you stop it.
"""
import asyncio
import threading
import time

import db
import graduation_watcher
import twitter_scanner
from config import ATTENTION_MENTION_THRESHOLD

_alerted = set()


def on_graduation(record):
    print(f"  -> now watching X for mentions of {record['symbol'] or record['mint']}")


def on_mentions(graduation_row, new_count):
    mint = graduation_row["mint"]
    symbol = graduation_row["symbol"] or mint
    total = len(db.mentions_for(mint))
    print(f"[x-mentions] {symbol}: +{new_count} new (total {total})")

    if total >= ATTENTION_MENTION_THRESHOLD and mint not in _alerted:
        _alerted.add(mint)
        print(f"\n*** HIGH ATTENTION: {symbol} has {total} X mentions since graduating -- {mint} ***\n")


def run_scanner_thread():
    # twitter_scanner uses blocking `requests`, so it gets its own thread
    # rather than sharing the asyncio loop with the websocket watcher.
    twitter_scanner.run_forever(on_mentions=on_mentions)


async def main():
    db.init_db()
    print("Starting fomo_x_signals: Ctrl+C to stop, `python correlate.py` for a report any time.\n")

    scanner_thread = threading.Thread(target=run_scanner_thread, daemon=True)
    scanner_thread.start()

    await graduation_watcher.watch(on_graduation=on_graduation)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
