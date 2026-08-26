"""SQLite storage shared by the watcher, scanner, and correlator."""
import sqlite3
import time
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS graduations (
    mint TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    graduated_at REAL NOT NULL,   -- unix timestamp (UTC), time we observed it
    raw_json TEXT,
    market_cap_usd REAL,             -- most recently refreshed market cap
    graduation_market_cap_usd REAL,  -- market cap at the moment we saw it graduate
    recent_velocity_pct REAL,        -- % change between the last two refreshes (is it moving *right now*)
    image_uri TEXT,                  -- token logo, from pump.fun's coin API
    creator TEXT,                    -- deployer wallet address, from pump.fun's coin API
    creator_total_coins INTEGER,     -- how many coins this wallet has launched (at graduation time)
    creator_graduated_coins INTEGER  -- how many of those actually graduated
);

CREATE TABLE IF NOT EXISTS new_tokens (
    mint TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    created_at REAL NOT NULL,
    raw_json TEXT,
    image_uri TEXT
);

CREATE TABLE IF NOT EXISTS mentions (
    tweet_id TEXT PRIMARY KEY,
    mint TEXT NOT NULL,
    author TEXT,
    text TEXT,
    posted_at REAL NOT NULL,      -- unix timestamp (UTC) from X
    observed_at REAL NOT NULL,    -- unix timestamp (UTC) when we fetched it
    matched_query TEXT,
    author_followers INTEGER,     -- from X's public_metrics, NULL if unavailable
    account_age_days REAL,        -- how old the posting account is, NULL if unavailable
    likely_bot INTEGER DEFAULT 0  -- 1 if it tripped the bot heuristic, see twitter_scanner.looks_like_bot()
);

CREATE INDEX IF NOT EXISTS idx_mentions_mint ON mentions(mint);

CREATE TABLE IF NOT EXISTS pre_launch_signals (
    tweet_id TEXT PRIMARY KEY,
    author TEXT,
    text TEXT,
    posted_at REAL NOT NULL,
    observed_at REAL NOT NULL,
    matched_query TEXT,
    author_followers INTEGER,
    account_age_days REAL,
    likely_bot INTEGER DEFAULT 0
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migration for DBs created before market cap / image tracking was added.
        for column, coltype in (
            ("market_cap_usd", "REAL"), ("graduation_market_cap_usd", "REAL"),
            ("recent_velocity_pct", "REAL"), ("image_uri", "TEXT"),
            ("creator", "TEXT"), ("creator_total_coins", "INTEGER"), ("creator_graduated_coins", "INTEGER"),
        ):
            try:
                conn.execute(f"ALTER TABLE graduations ADD COLUMN {column} {coltype}")
            except sqlite3.OperationalError:
                pass  # column already exists
        try:
            conn.execute("ALTER TABLE new_tokens ADD COLUMN image_uri TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists


def record_graduation(mint, symbol, name, raw_json, when=None, market_cap_usd=None, image_uri=None,
                       creator=None, creator_total_coins=None, creator_graduated_coins=None):
    when = when or time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO graduations
               (mint, symbol, name, graduated_at, raw_json, market_cap_usd, graduation_market_cap_usd, image_uri,
                creator, creator_total_coins, creator_graduated_coins)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(mint) DO NOTHING""",
            (mint, symbol, name, when, raw_json, market_cap_usd, market_cap_usd, image_uri,
             creator, creator_total_coins, creator_graduated_coins),
        )


def update_market_cap(mint, market_cap_usd, recent_velocity_pct=None, image_uri=None):
    with get_conn() as conn:
        conn.execute(
            """UPDATE graduations
               SET market_cap_usd = ?,
                   graduation_market_cap_usd = COALESCE(graduation_market_cap_usd, ?),
                   recent_velocity_pct = ?,
                   image_uri = COALESCE(?, image_uri)
               WHERE mint = ?""",
            (market_cap_usd, market_cap_usd, recent_velocity_pct, image_uri, mint),
        )


def record_new_token(mint, symbol, name, raw_json, when=None, image_uri=None):
    when = when or time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO new_tokens (mint, symbol, name, created_at, raw_json, image_uri)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(mint) DO NOTHING""",
            (mint, symbol, name, when, raw_json, image_uri),
        )


def update_new_token_image(mint, image_uri):
    if not image_uri:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE new_tokens SET image_uri = COALESCE(image_uri, ?) WHERE mint = ?",
            (image_uri, mint),
        )


def record_mention(tweet_id, mint, author, text, posted_at, matched_query, observed_at=None,
                    author_followers=None, account_age_days=None, likely_bot=False):
    observed_at = observed_at or time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO mentions
               (tweet_id, mint, author, text, posted_at, observed_at, matched_query,
                author_followers, account_age_days, likely_bot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tweet_id) DO NOTHING""",
            (tweet_id, mint, author, text, posted_at, observed_at, matched_query,
             author_followers, account_age_days, int(bool(likely_bot))),
        )


def recent_graduations(since_minutes=None):
    with get_conn() as conn:
        if since_minutes is None:
            rows = conn.execute("SELECT * FROM graduations ORDER BY graduated_at DESC").fetchall()
        else:
            cutoff = time.time() - since_minutes * 60
            rows = conn.execute(
                "SELECT * FROM graduations WHERE graduated_at >= ? ORDER BY graduated_at DESC",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]


def recent_new_tokens(since_minutes):
    """Tokens created recently that HAVEN'T graduated yet -- used to watch
    for X hype building before a token ever hits the market. Excludes
    anything that's already in the graduations table so it doesn't
    duplicate the main list once a watched token graduates."""
    with get_conn() as conn:
        cutoff = time.time() - since_minutes * 60
        rows = conn.execute(
            """SELECT * FROM new_tokens
               WHERE created_at >= ? AND mint NOT IN (SELECT mint FROM graduations)
               ORDER BY created_at DESC""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def mention_exists(tweet_id):
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM mentions WHERE tweet_id = ?", (tweet_id,)).fetchone()
        return row is not None


def pre_launch_signal_exists(tweet_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM pre_launch_signals WHERE tweet_id = ?", (tweet_id,)
        ).fetchone()
        return row is not None


def record_pre_launch_signal(tweet_id, author, text, posted_at, matched_query, observed_at=None,
                              author_followers=None, account_age_days=None, likely_bot=False):
    observed_at = observed_at or time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pre_launch_signals
               (tweet_id, author, text, posted_at, observed_at, matched_query,
                author_followers, account_age_days, likely_bot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(tweet_id) DO NOTHING""",
            (tweet_id, author, text, posted_at, observed_at, matched_query,
             author_followers, account_age_days, int(bool(likely_bot))),
        )


def recent_pre_launch_signals(since_minutes):
    with get_conn() as conn:
        cutoff = time.time() - since_minutes * 60
        rows = conn.execute(
            "SELECT * FROM pre_launch_signals WHERE posted_at >= ? ORDER BY posted_at DESC",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def mentions_for(mint):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mentions WHERE mint = ? ORDER BY posted_at ASC", (mint,)
        ).fetchall()
        return [dict(r) for r in rows]
