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
from config import PUMPPORTAL_API_KEY, MARKET_CAP_REFRESH_SEC

WS_URL = f"wss://pumpportal.fun/api/data?api-key={PUMPPORTAL_API_KEY}" if PUMPPORTAL_API_KEY else "wss://pumpportal.fun/api/data"


def _extract(event: dict, *keys, default=None):
    """Defensively pull the first matching key -- PumpPortal's exact field
    names have shifted before, so don't assume one fixed schema."""
    for k in keys:
        if k in event and event[k] not in (None, ""):
            return event[k]
    return default


_EMPTY_METADATA = {
    "symbol": None, "name": None, "market_cap_usd": None, "image_uri": None,
    "creator": None, "is_banned": False, "nsfw": False,
}


def _fetch_metadata(mint):
    """PumpPortal's migration event doesn't include the token's name/symbol,
    market cap, logo, creator wallet, or ban/nsfw status, so look them up
    from pump.fun's own public coin API as a fallback. Best effort only --
    any failure just leaves the fields blank rather than holding up the
    watcher loop. Returns a dict (not a tuple) since this keeps growing --
    positional unpacking was getting fragile."""
    try:
        resp = requests.get(
            f"https://frontend-api-v3.pump.fun/coins/{mint}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": data.get("symbol"),
            "name": data.get("name"),
            "market_cap_usd": data.get("usd_market_cap"),
            "image_uri": data.get("image_uri"),
            "creator": data.get("creator"),
            "is_banned": bool(data.get("is_banned")),
            "nsfw": bool(data.get("nsfw")),
        }
    except Exception:
        return dict(_EMPTY_METADATA)


def _fetch_market_cap(mint):
    return _fetch_metadata(mint)["market_cap_usd"]


def fetch_creator_track_record(creator):
    """How many coins has this wallet launched before, and how many of
    those actually graduated ("complete": true means it crossed the
    bonding-curve threshold and moved to a real DEX -- the same bar this
    whole app tracks)? Best effort: any failure returns (0, 0), which reads
    as "no track record" rather than crashing anything."""
    if not creator:
        return 0, 0
    try:
        resp = requests.get(
            "https://frontend-api-v3.pump.fun/coins",
            params={"creator": creator, "limit": 100},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        coins = resp.json()
        if not isinstance(coins, list):
            return 0, 0
        total = len(coins)
        graduated = sum(1 for c in coins if c.get("complete"))
        return total, graduated
    except Exception:
        return 0, 0


async def refresh_market_caps(interval_sec=MARKET_CAP_REFRESH_SEC):
    """Periodically re-fetches each tracked token's current market cap so the
    dashboard can show gain/loss since graduation, and how much it moved
    since the *previous* refresh -- that recent-velocity figure is what
    catches a push while it's happening, rather than only after the fact."""
    while True:
        for g in db.recent_graduations():
            meta = await asyncio.to_thread(_fetch_metadata, g["mint"])
            market_cap_usd, image_uri = meta["market_cap_usd"], meta["image_uri"]
            if market_cap_usd is None:
                continue
            previous = g["market_cap_usd"]
            recent_velocity_pct = None
            if previous:
                recent_velocity_pct = (market_cap_usd - previous) / previous * 100
            db.update_market_cap(g["mint"], market_cap_usd, recent_velocity_pct, image_uri=image_uri)
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
                        meta = await asyncio.to_thread(_fetch_metadata, mint)
                        if meta["is_banned"] or meta["nsfw"]:
                            # Legit trading platforms (fomo.family included)
                            # filter these out before ever showing them, so
                            # we skip recording it at all rather than
                            # showing something fomo wouldn't.
                            print(f"[graduation] skipped {symbol or mint} -- banned/nsfw on pump.fun")
                            continue
                        symbol = symbol or meta["symbol"]
                        name = name or meta["name"]
                        creator_total, creator_graduated = await asyncio.to_thread(fetch_creator_track_record, meta["creator"])
                        db.record_graduation(
                            mint, symbol, name, raw, when=now, market_cap_usd=meta["market_cap_usd"], image_uri=meta["image_uri"],
                            creator=meta["creator"], creator_total_coins=creator_total, creator_graduated_coins=creator_graduated,
                        )
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
