"""
Central config: env vars + the watchlist of accounts/keywords you care about.

Edit WATCH_ACCOUNTS / WATCH_KEYWORDS to match how you actually want to catch
"promising, big-upside, high-attention" tokens on X. Leaving both empty means
the scanner will only search by each graduated token's own symbol/contract
address, which is the safest (cheapest, least noisy) default.
"""
import os
from dotenv import load_dotenv

load_dotenv()

PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY", "")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")

MENTION_WATCH_WINDOW_MIN = int(os.getenv("MENTION_WATCH_WINDOW_MIN", "120"))
MENTION_POLL_INTERVAL_SEC = int(os.getenv("MENTION_POLL_INTERVAL_SEC", "90"))
ATTENTION_MENTION_THRESHOLD = int(os.getenv("ATTENTION_MENTION_THRESHOLD", "8"))

# Tokens whose market cap has crashed below this are hidden from the
# dashboard -- below this level a pump.fun token is effectively dead/rugged
# and just clutters the list.
MIN_MARKET_CAP_USD = int(os.getenv("MIN_MARKET_CAP_USD", "5000"))

DB_PATH = os.getenv("DB_PATH", "signals.db")

# Optional: specific X accounts (no @) whose posts about a token count extra,
# e.g. well-known callers/KOLs you personally trust. Leave empty to skip.
WATCH_ACCOUNTS = [
    # "someKOLhandle",
]

# Optional: extra keywords to OR into every token search (beyond the token's
# own symbol/contract address), e.g. "gem", "100x", "send it".
WATCH_KEYWORDS = [
    # "gem",
]
