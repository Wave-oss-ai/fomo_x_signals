"""
Joins graduation events with the X mentions collected for them, and prints a
report: when each token graduated, how much X attention it got, and whether
that attention showed up before or after graduation.

Run standalone: `python correlate.py` (prints a report for all graduations
currently in the DB). Also importable -- main.py calls attention_score() live.
"""
import time

import db

LOCAL_FMT = "%Y-%m-%d %H:%M:%S"


def _local(ts):
    return time.strftime(LOCAL_FMT, time.localtime(ts)) if ts else "-"


def attention_score(mint):
    """Heuristic attention read -- NOT a price prediction, just a transparent
    score built from data we actually have. Mentions flagged as likely-bot
    (see twitter_scanner.looks_like_bot()) are excluded before any of this
    math runs, so the score reflects likely real people, not spam volume:

      - volume:    how many (human-likely) X mentions total (capped, so one
                    viral token doesn't blow the scale for everything else)
      - spread:    how many DIFFERENT people posted, not just one account
                    repeating itself
      - velocity:  what fraction of all mentions landed in the last 10
                    minutes -- rewards attention that's accelerating right now
      - early bird: +10 flat if any mention landed BEFORE graduation (organic
                    anticipation, as opposed to only post-hype chasing)

    Score is 0-100. It measures social attention, nothing else -- it cannot
    and does not distinguish a genuinely trending token from a coordinated
    pump (the bot filter catches obvious automation, not a determined human
    coordinating manually). Treat it as a starting point for your own
    research, not a signal.
    """
    all_mentions = db.mentions_for(mint)
    bot_count = sum(1 for m in all_mentions if m.get("likely_bot"))
    mentions = [m for m in all_mentions if not m.get("likely_bot")]

    if not mentions:
        return {
            "count": 0, "first_mention_at": None, "lead_seconds": None,
            "distinct_authors": 0, "score": 0, "band": "None",
            "pattern": "No data", "bot_mentions_excluded": bot_count,
        }

    grad = next((g for g in db.recent_graduations() if g["mint"] == mint), None)
    first_at = mentions[0]["posted_at"]
    lead = (grad["graduated_at"] - first_at) if grad else None

    count = len(mentions)
    distinct_authors = len({m["author"] for m in mentions if m["author"]})

    now = time.time()
    recent_count = sum(1 for m in mentions if now - m["posted_at"] <= 600)  # last 10 min
    velocity_fraction = recent_count / count if count else 0

    volume_pts = min(count, 10) * 3          # up to 30
    spread_pts = min(distinct_authors, 6) * 5  # up to 30
    velocity_pts = round(velocity_fraction * 25)  # up to 25
    early_pts = 10 if (lead is not None and lead > 0) else 0  # up to 10
    base_pts = 5 if count > 0 else 0          # up to 5

    score = min(100, volume_pts + spread_pts + velocity_pts + early_pts + base_pts)

    if score >= 75:
        band = "Very High"
    elif score >= 50:
        band = "High"
    elif score >= 25:
        band = "Moderate"
    else:
        band = "Low"

    # "Pattern": is the buzz coming from a lot of different people, or a
    # handful of accounts posting repeatedly? NOT a safety rating -- every
    # token here is high-risk regardless of pattern. This only flags whether
    # the online activity looks spread-out (harder to fake at scale) or
    # concentrated (the shape you'd expect from a bot ring or a couple of
    # accounts coordinating a pump). Needs a handful of mentions before it's
    # a meaningful read at all.
    concentration = distinct_authors / count if count else 0
    if count < 3:
        pattern = "Not enough data"
    elif concentration >= 0.6:
        pattern = "Broader interest"
    elif concentration <= 0.35:
        pattern = "Concentrated activity"
    else:
        pattern = "Mixed"

    return {
        "count": count,
        "first_mention_at": first_at,
        "lead_seconds": lead,
        "distinct_authors": distinct_authors,
        "score": score,
        "band": band,
        "pattern": pattern,
        "bot_mentions_excluded": bot_count,
    }


def report(since_minutes=None):
    graduations = db.recent_graduations(since_minutes=since_minutes)
    rows = []
    for g in graduations:
        stats = attention_score(g["mint"])
        rows.append((g, stats))

    rows.sort(key=lambda r: r[1]["score"], reverse=True)

    print(f"{'SYMBOL':<12}{'SCORE':<8}{'BAND':<12}{'MENTIONS':<10}{'AUTHORS':<9}{'BOTS EXCL':<11}{'GRADUATED':<21}MINT")
    for g, stats in rows:
        print(
            f"{(g['symbol'] or '?'):<12}{stats['score']:<8}{stats['band']:<12}"
            f"{stats['count']:<10}{stats['distinct_authors']:<9}{stats['bot_mentions_excluded']:<11}"
            f"{_local(g['graduated_at']):<21}{g['mint']}"
        )

    return rows


if __name__ == "__main__":
    db.init_db()
    report()
