"""
Polls X (Twitter) for mentions of tokens that have recently graduated (or, if
you add mints to WATCHLIST manually, any token you want to track pre-emptively).

Uses the official X API v2 "recent search" endpoint. As of 2026 X has no free
tier -- every read is billed (~$0.005/tweet), so this module is deliberately
cost-bounded:
  - it only searches for tokens seen in the last MENTION_WATCH_WINDOW_MIN,
  - it polls each token at most once every MENTION_POLL_INTERVAL_SEC,
  - it stops polling a token once it ages out of the watch window.

If you'd rather use a cheaper reseller (GetXAPI, TwitterAPI.io, Xpoz, etc.),
replace the body of `search_recent()` with that provider's request/response
shape -- everything else in this file (dedup, cost bounding, DB writes) stays
the same.
"""
import calendar
import re
import time

import requests

import db
from config import (
    X_BEARER_TOKEN,
    MENTION_WATCH_WINDOW_MIN,
    MENTION_POLL_INTERVAL_SEC,
    WATCH_ACCOUNTS,
    WATCH_KEYWORDS,
)

SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


def build_query(symbol, mint):
    """OR together the token's cashtag/name, its contract address, and any
    trusted accounts/keywords from config.py. X search queries have a length
    cap, so keep this focused rather than throwing in everything."""
    terms = []
    if symbol:
        terms.append(f"${symbol}")
    terms.append(mint)  # contract address is the least ambiguous signal
    for kw in WATCH_KEYWORDS:
        terms.append(kw)
    query = " OR ".join(f'"{t}"' if " " in t else t for t in terms)

    if WATCH_ACCOUNTS:
        accounts = " OR ".join(f"from:{a}" for a in WATCH_ACCOUNTS)
        query = f"({query}) OR ({accounts} {symbol or mint})"

    return f"({query}) -is:retweet"


def search_recent(query, max_results=25):
    """Returns (tweets, users_by_id). users_by_id maps author_id -> that
    author's user object (username, account age, follower count, etc.),
    fetched via X API v2's `expansions` in the same request -- no extra
    billed reads, it just asks for author info alongside the tweets."""
    if not X_BEARER_TOKEN:
        raise RuntimeError("X_BEARER_TOKEN is not set -- see .env.example")

    resp = requests.get(
        SEARCH_URL,
        headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"},
        params={
            "query": query,
            "max_results": max_results,
            "tweet.fields": "created_at,author_id",
            "expansions": "author_id",
            "user.fields": "created_at,public_metrics,username",
        },
        timeout=15,
    )
    if resp.status_code == 429:
        print("[twitter_scanner] rate limited, backing off")
        time.sleep(30)
        return [], {}
    resp.raise_for_status()
    body = resp.json()
    tweets = body.get("data", [])
    users = {u["id"]: u for u in body.get("includes", {}).get("users", [])}
    return tweets, users


def _to_epoch(created_at_iso):
    """X returns UTC timestamps like '2026-08-21T12:34:56.000Z'; timegm treats
    the parsed struct as UTC instead of local time (unlike mktime)."""
    return calendar.timegm(time.strptime(created_at_iso, "%Y-%m-%dT%H:%M:%S.000Z"))


_TRAILING_DIGITS = re.compile(r"\d{6,}$")  # e.g. "cryptofan38271940" -- a common auto-generated handle shape


def looks_like_bot(user, now=None):
    """Heuristic, not certainty -- flags accounts that show the SHAPE of
    automated/spam behavior, using only what X's public user object gives us
    for free alongside the tweet search:

      - very new account posting at a very high volume (classic burner/bot
        ring pattern -- a real person rarely tweets hundreds of times in
        their first month)
      - zero followers with an unusually high tweet count (posts into the
        void at scale, nobody follows back -- automation, not a person
        building an audience)
      - a username ending in a long string of digits (the default shape
        Twitter/X assigns when someone doesn't pick a real handle, common
        in mass-created accounts)

    This will sometimes misflag a genuine very-new enthusiastic user, and
    won't catch a well-disguised bot -- it's a signal to weight, not proof.
    """
    if not user:
        return False  # no user data came back; don't penalize what we can't see

    now = now or time.time()
    metrics = user.get("public_metrics", {}) or {}
    tweet_count = metrics.get("tweet_count", 0) or 0
    followers = metrics.get("followers_count", 0) or 0
    username = user.get("username", "") or ""

    account_age_days = None
    created_at = user.get("created_at")
    if created_at:
        try:
            account_age_days = (now - _to_epoch(created_at)) / 86400
        except Exception:
            account_age_days = None

    if account_age_days is not None and account_age_days < 30 and tweet_count > 500:
        return True
    if followers == 0 and tweet_count > 1000:
        return True
    if _TRAILING_DIGITS.search(username):
        return True
    return False


def poll_once(on_mentions=None):
    """One sweep: for every graduation still inside the watch window, search
    X and store any new tweets. Call this in a loop from main.py."""
    graduations = db.recent_graduations(since_minutes=MENTION_WATCH_WINDOW_MIN)
    for g in graduations:
        query = build_query(g["symbol"], g["mint"])
        try:
            tweets, users = search_recent(query)
        except Exception as e:
            print(f"[twitter_scanner] search failed for {g['symbol'] or g['mint']}: {e}")
            continue

        new_count = 0
        for t in tweets:
            if db.mention_exists(t["id"]):
                continue
            try:
                posted_at = _to_epoch(t["created_at"])
            except Exception:
                posted_at = time.time()

            user = users.get(t.get("author_id"))
            followers = None
            account_age_days = None
            if user:
                followers = (user.get("public_metrics") or {}).get("followers_count")
                created_at = user.get("created_at")
                if created_at:
                    try:
                        account_age_days = (time.time() - _to_epoch(created_at)) / 86400
                    except Exception:
                        account_age_days = None

            db.record_mention(
                tweet_id=t["id"],
                mint=g["mint"],
                author=user.get("username") if user else t.get("author_id"),
                text=t.get("text", ""),
                posted_at=posted_at,
                matched_query=query,
                author_followers=followers,
                account_age_days=account_age_days,
                likely_bot=looks_like_bot(user),
            )
            new_count += 1

        if new_count and on_mentions:
            on_mentions(g, new_count)


def run_forever(on_mentions=None):
    while True:
        poll_once(on_mentions=on_mentions)
        time.sleep(MENTION_POLL_INTERVAL_SEC)


if __name__ == "__main__":
    db.init_db()
    run_forever()
