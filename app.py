"""
One-file, one-command version of this project: run this (or double-click
start.bat, which runs this for you) and it handles everything --
first-time API key setup, the graduation watcher, the X mention scanner,
and the web dashboard, then opens your browser to it automatically.

    python app.py

Leave the window open while it runs. Ctrl+C (or just close the window) stops
everything. main.py / dashboard.py still exist separately if you'd rather
run the collector and the dashboard in two windows, but you don't need to.

This same file also runs unmodified on a hosting platform (Replit, Render,
etc.) -- see README.md's "Hosting it online" section. When PUMPPORTAL_API_KEY
/ X_BEARER_TOKEN are already provided as real environment variables (which is
how Replit "Secrets" and Render "Environment" work), the interactive prompt
below is skipped automatically, it binds to the $PORT the host assigns
instead of a fixed port, and it won't try to open a local browser.
"""
import os
import sys
import threading
import time
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

# Hosting platforms set PORT themselves; running locally, we default to 8787.
IS_HOSTED = "PORT" in os.environ
PORT = int(os.environ.get("PORT", 8787))


def ensure_env():
    """First run only: ask for the two API keys and save them to .env, so
    nobody has to open Notepad and edit a config file by hand. Skipped
    entirely when the keys already exist as real environment variables
    (hosting "Secrets"/"Environment" settings) or when there's no
    interactive terminal to prompt on (running on a host)."""
    if os.environ.get("PUMPPORTAL_API_KEY") and os.environ.get("X_BEARER_TOKEN"):
        return
    if ENV_PATH.exists():
        return
    if IS_HOSTED or not sys.stdin.isatty():
        print("No API keys found. Set PUMPPORTAL_API_KEY and X_BEARER_TOKEN as "
              "environment variables/secrets in your hosting platform's dashboard.")
        return

    print("=" * 64)
    print(" First-time setup -- two API keys needed (see README.md for")
    print(" exactly how to get each one -- it only takes a few minutes):")
    print("=" * 64)
    pumpportal_key = input("\n1) PumpPortal API key (free -- pumpportal.fun): ").strip()
    x_bearer = input("2) X (Twitter) Bearer Token (developer.x.com): ").strip()

    with open(ENV_PATH, "w") as f:
        f.write(f"PUMPPORTAL_API_KEY={pumpportal_key}\n")
        f.write(f"X_BEARER_TOKEN={x_bearer}\n")
        f.write("MENTION_WATCH_WINDOW_MIN=120\n")
        f.write("MENTION_POLL_INTERVAL_SEC=90\n")
        f.write("ATTENTION_MENTION_THRESHOLD=8\n")

    print("\nSaved to .env -- you won't be asked again on this computer.")
    print("(To change a key later, edit the .env file in this folder.)\n")


ensure_env()

# Everything below reads .env via config.py's load_dotenv(), so it must come
# after ensure_env() has had a chance to create the file.
import asyncio  # noqa: E402

import db  # noqa: E402
import graduation_watcher  # noqa: E402
import twitter_scanner  # noqa: E402
from dashboard import app as flask_app  # noqa: E402
from config import ATTENTION_MENTION_THRESHOLD, ENABLE_PRE_MARKET_SCAN, ENABLE_PRE_LAUNCH_SCAN  # noqa: E402

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


def run_scanner():
    twitter_scanner.run_forever(on_mentions=on_mentions)


def on_pre_market_mentions(new_token_row, new_count):
    symbol = new_token_row["symbol"] or new_token_row["mint"]
    print(f"[pre-market] {symbol}: +{new_count} new mention(s) before graduation")


def run_pre_market_scanner():
    twitter_scanner.run_forever_new_tokens(on_mentions=on_pre_market_mentions)


def on_pre_launch_signal(new_count):
    print(f"[pre-launch] +{new_count} new pre-launch signal(s) found")


def run_pre_launch_scanner():
    twitter_scanner.run_forever_pre_launch(on_signal=on_pre_launch_signal)


def run_dashboard():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def main():
    db.init_db()
    print("Starting fomo_x_signals...")
    if IS_HOSTED:
        print(f"Serving on port {PORT}.")
    else:
        print("Your browser will open to the dashboard in a couple seconds.")
    print("Leave this window open -- closing it (or Ctrl+C) stops everything.\n")

    threading.Thread(target=run_scanner, daemon=True).start()
    if ENABLE_PRE_MARKET_SCAN:
        threading.Thread(target=run_pre_market_scanner, daemon=True).start()
    else:
        print("[pre-market] disabled -- set ENABLE_PRE_MARKET_SCAN=1 to turn on pre-graduation X hype scanning")
    if ENABLE_PRE_LAUNCH_SCAN:
        threading.Thread(target=run_pre_launch_scanner, daemon=True).start()
    else:
        print("[pre-launch] disabled -- set ENABLE_PRE_LAUNCH_SCAN=1 to turn on pre-launch chatter scanning")
    threading.Thread(target=run_dashboard, daemon=True).start()

    if not IS_HOSTED:
        time.sleep(2)
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")

    async def run_watchers():
        await asyncio.gather(
            graduation_watcher.watch(on_graduation=on_graduation),
            graduation_watcher.refresh_market_caps(),
        )

    asyncio.run(run_watchers())  # runs forever


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
