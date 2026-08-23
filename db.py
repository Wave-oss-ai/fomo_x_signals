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
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS new_tokens (
    mint TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    created_at REAL NOT NULL,
    raw_json TEXT
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


def record_graduation(mint, symbol, name, raw_json, when=None):
    when = when or time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO graduations (mint, symbol, name, graduated_at, raw_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(mint) DO NOTHING""",
            (mint, symbol, name, when, raw_json),
        )


def record_new_token(mint, symbol, name, raw_json, when=None):
    when = when or time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO new_tokens (mint, symbol, name, created_at, raw_json)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(mint) DO NOTHING""",
            (mint, symbol, name, when, raw_json),
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


def mention_exists(tweet_id):
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM mentions WHERE tweet_id = ?", (tweet_id,)).fetchone()
        return row is not None


def mentions_for(mint):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mentions WHERE mint = ? ORDER BY posted_at ASC", (mint,)
        ).fetchall()
        return [dict(r) for r in rows]
