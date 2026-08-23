"""
Watches Solana pump.fun-style token launches and "graduations" (bonding-curve
tokens crossing the market-cap threshold and moving to a real DEX) via
PumpPortal's free real-time WebSocket feed: https://pumpportal.fun/data-api/real-time/

Fomo (fomo.family) itself doesn't appear to publish a public API for its
"graduated" feed, but Fomo's graduated-token list is populated from these same
underlying launchpad programs, so watching the launchpad directly gets you the
graduation *moment* reliably. If you find Fomo does expose an API/webhook
later, swap this module out and keep the same db.record_graduation() calls.

Run standalone for testing: `python graduation_watcher.py`
"""
import asyncio
import json
import time

import requests
import websockets

import db
from config import PUMPPORTAL_API_KEY

WS_URL = f"wss://pumpportal.fun/api/data?api-key={PUMPPORTAL_API_KEY}" if PUMPPORTAL_API_KEY else "wss://pumpportal.fun/api/data"


def _extract(event: dict, *keys, default=None):
    """Defensively pull the first matching key -- PumpPortal's exact field
    names have shifted before, so don't assume one fixed schema."""
    for k in keys:
        if k in event and event[k] not in (None, ""):
            return event[k]
    return default


def _fetch_metadata(mint):
    """PumpPortal's migration event doesn't include the token's name/symbol
    or market cap, so look them up from pump.fun's own public coin API as a
    fallback. Best effort only -- any failure just leaves the fields blank
    rather than holding up the watcher loop."""
    try:
        resp = requests.get(
            f"https://frontend-api-v3.pump.fun/coins/{mint}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("symbol"), data.get("name"), data.get("usd_market_cap")
    except Exception:
        return None, None, None


def _fetch_market_cap(mint):
    _, _, market_cap_usd = _fetch_metadata(mint)
    return market_cap_usd


async def refresh_market_caps(interval_sec=30):
    """Periodically re-fetches each tracked token's current market cap so the
    dashboard can show gain/loss since graduation."""
    while True:
        for g in db.recent_graduations():
            market_cap_usd = await asyncio.to_thread(_fetch_market_cap, g["mint"])
            if market_cap_usd is not None:
                db.update_market_cap(g["mint"], market_cap_usd)
        await asyncio.sleep(interval_sec)


async def watch(on_graduation=None, on_new_token=None, reconnect_delay=5):
    """Connects, subscribes to the free streams, and stores events forever.

    on_graduation(dict) / on_new_token(dict) are optional callbacks invoked
    with the parsed record right after it's written to the DB (used by
    main.py to print live alerts).
    """
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                await ws.send(json.dumps({"method": "subscribeMigration"}))
                print("[graduation_watcher] connected, subscribed to new-token + migration streams")

                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    mint = _extract(event, "mint", "mintAddress", "tokenMint", "ca")
                    if not mint:
                        continue

                    symbol = _extract(event, "symbol", "ticker")
                    name = _extract(event, "name")
                    now = time.time()

                    kind = str(_extract(event, "txType", "type", "method", default="")).lower()
                    is_migration = "migrat" in kind or "graduat" in kind or event.get("pool") == "pump-amm"

                    if is_migration:
                        fetched_symbol, fetched_name, market_cap_usd = await asyncio.to_thread(_fetch_metadata, mint)
                        symbol = symbol or fetched_symbol
                        name = name or fetched_name
                        db.record_graduation(mint, symbol, name, raw, when=now, market_cap_usd=market_cap_usd)
                        record = {"mint": mint, "symbol": symbol, "name": name, "graduated_at": now}
                        print(f"[graduation] {symbol or mint} graduated at {time.strftime('%H:%M:%S', time.localtime(now))}")
                        if on_graduation:
                            on_graduation(record)
                    else:
                        db.record_new_token(mint, symbol, name, raw, when=now)
                        if on_new_token:
                            on_new_token({"mint": mint, "symbol": symbol, "name": name, "created_at": now})

        except Exception as e:
            # Broad on purpose: this runs unattended (often 24/7 on a host),
            # so ANY connection-phase failure -- a bad/missing API key, DNS
            # hiccup, proxy/firewall block, PumpPortal-side outage, or a
            # websockets library error we didn't anticipate -- should log
            # and retry, never take down the whole app. A narrower except
            # here previously let an unexpected error crash the entire
            # process, dashboard and all.
            print(f"[graduation_watcher] {type(e).__name__}: {e} -- reconnecting in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)


if __name__ == "__main__":
    db.init_db()
    asyncio.run(watch())
