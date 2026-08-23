# fomo_x_signals

Watches Solana pump.fun-style token "graduations" (the moment a bonding-curve
token crosses its market-cap threshold and moves to a real DEX -- this is the
same event that populates Fomo's "graduated" tab) and cross-references each
one against X (Twitter) mentions, so you can see how much attention a token
was getting and whether that attention started before or after it graduated.

## Why it's built this way

**Fomo itself doesn't have a public API** (at least none I could find in its
docs/marketing site as of August 2026). What Fomo shows as "graduated" is
sourced from the underlying launchpad programs on whichever chain the token
launched on. The most mature and best-documented of these is **pump.fun on
Solana**, which has a free real-time feed via
[PumpPortal](https://pumpportal.fun/data-api/real-time/). That's what
`graduation_watcher.py` uses. If most of what you trade on Fomo is Solana
tokens, this will line up closely with what you see in the app. If Fomo later
publishes its own API, or you're mostly trading Base/BNB/Monad tokens, that
part needs different data sources -- ping me and I'll adapt it.

**X (Twitter) has no free tier as of 2026** -- every read costs money
(~$0.005/tweet via the official API). `twitter_scanner.py` is written against
the official X API v2, and is deliberately cost-bounded: it only searches for
tokens that graduated in the last `MENTION_WATCH_WINDOW_MIN` minutes, and only
polls each one every `MENTION_POLL_INTERVAL_SEC` seconds. Tune those in `.env`
to control spend. If you'd rather use a cheaper reseller (GetXAPI ~$0.05/1000
tweets, TwitterAPI.io, Xpoz's free tier), swap the request in
`twitter_scanner.search_recent()` for that provider's API -- everything else
(DB writes, cost bounding, the report) stays the same.

## Easiest way to run it (Windows)

1. Get your two API keys first (both are quick):
   - **PumpPortal** (free) -- sign up at https://pumpportal.fun and grab your API key.
   - **X (Twitter)** -- create a project at https://developer.x.com and copy its Bearer
     Token. This one isn't free (reads run ~$0.005 each), see "Why it's built this
     way" above.
2. Double-click **`start.bat`** in this folder.
   - First time: it installs Python packages automatically, then asks you to paste
     in your two API keys right there in the window. After that it remembers them
     (saved to a `.env` file in this folder) -- you won't be asked again.
   - Your browser opens automatically to the dashboard.
   - Leave the black window open; that's what's actually running. Closing it stops
     everything.
   - If Windows says Python isn't installed, it'll open the download page for you --
     run that installer, check **"Add python.exe to PATH"**, then double-click
     `start.bat` again.

That's it -- one file, one click (plus pasting in two keys the first time).

## Manual way (any OS, more control)

```bash
cd fomo_x_signals
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env` with the same two keys described above. Optionally edit
`config.py`'s `WATCH_ACCOUNTS` / `WATCH_KEYWORDS` if there are specific
callers/KOLs or keywords you want weighted into every search.

Then either run everything in one process, same as `start.bat` does:

```bash
python app.py
```

or run the collector and the dashboard as two separate pieces, in two
terminals, if you want to keep an eye on the collector's log output
separately from the browser view:

```bash
python main.py        # terminal 1: collects graduations + X mentions
python dashboard.py    # terminal 2: serves http://localhost:8787
```

Either way, everything is saved to `signals.db` (SQLite), so at any point you
can also get a plain-text report:

```bash
python correlate.py
```

which prints a table of every graduated token, its X mention count, when the
first mention landed, and whether that was before ("early") or after
graduation. The dashboard at **http://localhost:8787** shows the same thing
live, auto-refreshing every 5 seconds. It's local only -- nothing is uploaded
anywhere.

## Attention Score, tabs, and bot filtering

The dashboard (and `embed_live.html`, `index.html`, `artifact_dashboard.html`)
now show three things beyond a raw mention count, all computed in
`correlate.py`:

- **Attention Score (0-100)** -- a transparent heuristic built from how many
  people mentioned a token, how many *different* people (not just one account
  repeating itself), how fast mentions are landing right now, and whether any
  mention came in before graduation. It is **not** a price prediction and
  can't tell a genuinely trending token from a coordinated pump -- it only
  measures how much (human-looking) buzz there is.
- **Broader Interest / Concentrated Activity tabs** -- click either tab on
  the dashboard to filter to tokens whose mentions came from a spread-out
  group of accounts ("Broader interest") versus one or two accounts posting
  repeatedly ("Concentrated activity"). This is **not a safety rating** --
  every token is high-risk either way, it's just a read on whether the
  activity looks organic or narrow.
- **Bot filtering** -- before any of the above is computed, `twitter_scanner.py`
  checks each X account that mentioned a token against a heuristic
  (`looks_like_bot()`): a brand-new account posting at very high volume, an
  account with zero followers but a huge tweet count, or a username ending in
  a long string of digits (a common auto-generated-handle shape). Mentions
  from flagged accounts are excluded from the score, the mention count, and
  the distinct-author count -- the dashboard shows how many were filtered out
  under each token's mention count. This is a heuristic, not certainty: it can
  miss a well-disguised bot and can occasionally misflag a genuine brand-new
  user. It only runs on the live version (`app.py`/`main.py`), since it needs
  the X API's account data -- the no-API-key preview (`preview.py`,
  `index.html`) just seeds a couple of bot-shaped sample accounts so you can
  see what the filtered note looks like.

## Hosting it online (so a pasted-into-a-website version shows real data)

Everything above runs on your own computer, which is the simplest and free
way to use this. But a page you paste into a website builder's "embed HTML"
block has no computer running behind it -- it can only show a snapshot, not
live-updating data, unless the actual data-collecting program (`app.py`) is
running somewhere online 24/7 that the page can fetch from.

**Replit is the easiest way to do that** -- no git, no command line, just
paste code into a browser and click Run:

1. Go to replit.com and create a free account.
2. Click **Create App** (or **+ Create Repl**), choose **Python**, give it any name.
3. Delete whatever starter file it creates, then recreate this project's files
   inside it: for each `.py` file in this folder (`app.py`, `db.py`, `config.py`,
   `correlate.py`, `dashboard.py`, `graduation_watcher.py`, `twitter_scanner.py`)
   plus `requirements.txt`, create a matching file in Replit's file list and
   paste the contents in.
4. In Replit's left sidebar, open **Secrets** (the padlock icon) and add two:
   `PUMPPORTAL_API_KEY` and `X_BEARER_TOKEN`, with your real keys as the
   values. This keeps them out of your code entirely.
5. Click **Run**. The console will print a URL like
   `https://your-repl-name.your-username.repl.co` -- that's your live app.
6. To keep it running even when you close the browser tab, Replit's
   "Deployments" feature (small monthly cost) keeps it up permanently; the
   free Run mode stays up only while that browser tab is open, which is fine
   for testing.
7. Open `embed_live.html` in a text editor, find the line near the top of its
   `<script>` that says `const API_BASE = "PASTE_YOUR_HOSTED_URL_HERE";`, and
   replace the placeholder with your actual Replit URL from step 5 (no
   trailing slash). Then paste `embed_live.html`'s contents into your website
   builder's embed/custom-HTML block, same as before -- it'll now fetch real
   data from your hosted app every 5 seconds instead of showing sample numbers.

Render.com or Railway.app work too if you'd rather use one of those instead
(both read the included `Procfile`), but they expect your code in a GitHub
repository rather than pasted directly in, which is an extra step Replit
skips.

## Honest limitations

- **This is attention tracking, not a prediction of price.** A token getting
  a lot of X mentions after graduating is exactly the pattern you'd see both
  for a genuinely trending token *and* for a coordinated pump-and-dump. The
  script can't tell those apart -- that judgment call is still yours.
- Contract-address search on X will miss mentions that only use the token's
  name/symbol before the CA is widely known, and symbol search can collide
  with unrelated tickers. Tighten `build_query()` in `twitter_scanner.py` if
  you're getting noise.
- PumpPortal's event field names have changed before; `graduation_watcher.py`
  parses defensively but double-check `signals.db`'s `raw_json` column if a
  graduation looks like it's missing a symbol/name.
- This isn't financial advice, and I'm not a financial advisor -- memecoin/
  bonding-curve trading is high-risk (rug pulls, wash trading, and manufactured
  social hype are all common in this space). Treat any alert here as a
  starting point for your own research, not a signal to act on directly.
