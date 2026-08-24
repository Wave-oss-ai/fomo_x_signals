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
MENTION_POLL_INTERVAL_SEC = int(os.getenv("MENTION_POLL_INTERVAL_SEC", "300"))
ATTENTION_MENTION_THRESHOLD = int(os.getenv("ATTENTION_MENTION_THRESHOLD", "8"))

# Tokens whose market cap has crashed below this are hidden from the
# dashboard -- below this level a pump.fun token is effectively dead/rugged
# and just clutters the list.
MIN_MARKET_CAP_USD = int(os.getenv("MIN_MARKET_CAP_USD", "5000"))

# A token whose market cap jumps at least this much (%) between two
# consecutive refreshes gets flagged "High Priority" -- this catches a push
# WHILE it's happening (recent velocity), not just after it's already run
# up. Not a prediction it'll keep moving.
HIGH_PRIORITY_VELOCITY_PCT = int(os.getenv("HIGH_PRIORITY_VELOCITY_PCT", "20"))

DB_PATH = os.getenv("DB_PATH", "signals.db")

# How often (seconds) to re-check each tracked token's market cap. Free
# (pump.fun's own public API, no billing), so this can run tight without
# adding to X API spend.
MARKET_CAP_REFRESH_SEC = int(os.getenv("MARKET_CAP_REFRESH_SEC", "10"))

# Pre-market watch: search X for mentions of tokens that were just CREATED
# on pump.fun, before they've graduated -- catches hype building early. Kept
# short/slow by default on purpose: there are far more new token launches
# than graduations, so watching all of them for as long/as often as
# graduated tokens would multiply X API spend fast.
PRE_MARKET_WATCH_WINDOW_MIN = int(os.getenv("PRE_MARKET_WATCH_WINDOW_MIN", "15"))
PRE_MARKET_POLL_INTERVAL_SEC = int(os.getenv("PRE_MARKET_POLL_INTERVAL_SEC", "180"))

# Off by default -- new pump.fun launches vastly outnumber graduations, so
# this can burn through X API spend much faster than graduation-only
# tracking. Set to "1" (as an env var/Secret) once you're ready to pay for it.
ENABLE_PRE_MARKET_SCAN = os.getenv("ENABLE_PRE_MARKET_SCAN") == "1"

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

# Pre-launch chatter: tokens don't have a mint/contract address until they're
# actually created on-chain, so this can't search by symbol -- it searches
# X purely for phrases/accounts that tend to precede a launch. A separate
# list from WATCH_KEYWORDS/WATCH_ACCOUNTS above so these phrases don't also
# get mixed into every graduated-token search (that would just add noise
# there). Edit freely -- these are a reasonable starting set.
PRE_LAUNCH_KEYWORDS = [
    "stealth launch",
    "launching soon",
    "CA soon",
    "fair launch",
    "dropping soon",
]
PRE_LAUNCH_ACCOUNTS = [
    # "someKOLhandle",
]

# Off by default -- this is a THIRD X polling stream on top of graduated
# mentions and pre-market hype, so it stacks more spend on top of both.
# Set to "1" (as an env var/Secret) once you're ready to pay for it.
ENABLE_PRE_LAUNCH_SCAN = os.getenv("ENABLE_PRE_LAUNCH_SCAN") == "1"
PRE_LAUNCH_POLL_INTERVAL_SEC = int(os.getenv("PRE_LAUNCH_POLL_INTERVAL_SEC", "300"))
