"""
Preview mode: NO API keys needed. Seeds the dashboard with realistic sample
data (fake tokens, fake graduation times, fake tweets) purely so you can see
what the dashboard looks like, then opens it in your browser.

This does NOT connect to PumpPortal or X -- nothing here is real data. For
the actual live version, use start.bat / app.py instead (needs the two API
keys described in README.md).

    python preview.py   (or just double-click preview.bat)
"""
import os

# Keep sample data in its own file so it never touches a real signals.db
# from an actual run of app.py/main.py.
os.environ["DB_PATH"] = "demo_signals.db"
os.environ["FOMO_DEMO_MODE"] = "1"

import threading
import time
import webbrowser

import db

DEMO_DB_FILE = "demo_signals.db"
if os.path.exists(DEMO_DB_FILE):
    os.remove(DEMO_DB_FILE)

db.init_db()


def seed_demo_data():
    """A handful of fake tokens covering the interesting cases: high
    attention, low attention, zero mentions, and mentions that started
    before graduation vs. after -- so the dashboard looks like something
    real is happening."""
    now = time.time()

    tokens = [
        ("DemoMintAAA111", "MOONPUP", "Moon Pup", 1400, [
            (1900, "cryptowhale22", "keep an eye on $MOONPUP, chart looks insane"),
            (1350, "degen_caller", "$MOONPUP just graduated!! sending it"),
            (1200, "sol_sniper", "loaded a bag of $MOONPUP"),
            (1000, "apegod", "$MOONPUP volume going parabolic"),
            (800, "cryptowhale22", "still holding $MOONPUP, up big"),
            (600, "newtrader99", "wait is $MOONPUP legit or a rug"),
            (400, "degen_caller", "$MOONPUP holders up 3x since graduation"),
            (250, "apegod", "everyone talking about $MOONPUP rn"),
            (100, "sol_sniper", "$MOONPUP still pumping"),
            # A couple of bot-shaped accounts mixed in, so the preview shows
            # what filtered-out spam looks like (these are excluded from the
            # score/mention count, same as the live version would do).
            (90, "moonpup_buy88427193", "$MOONPUP 100x guaranteed buy now", True),
            (60, "cryptobot4471029384", "$MOONPUP to the moon buy now link in bio", True),
        ]),
        ("DemoMintBBB222", "CATX", "Cat X", 900, [
            (850, "randomuser1", "$CATX just launched, looks mid"),
        ]),
        ("DemoMintCCC333", "RUGWARN", "Rug Warn Token", 300, []),
        ("DemoMintDDD444", "FROGKING", "Frog King", 2200, [
            (2600, "kol_frogfan", "$FROGKING about to send, watch this one"),
            (2500, "kol_frogfan", "calling it now, $FROGKING before it graduates"),
            (2100, "sol_sniper", "$FROGKING graduated, told you"),
            (1900, "apegod", "$FROGKING up huge"),
            (1700, "degen_caller", "$FROGKING is the play today"),
            (1500, "newtrader99", "just aped $FROGKING"),
            (1300, "cryptowhale22", "$FROGKING mooning"),
            (1100, "sol_sniper", "$FROGKING still going"),
            (900, "apegod", "$FROGKING to the moon fr"),
            (700, "degen_caller", "$FROGKING best call this week"),
        ]),
    ]

    # Simple colored-circle "logos" (inline SVG data URIs) so the preview
    # demonstrates the token-avatar UI without depending on any real image host.
    colors = ["#5b8def", "#e0653a", "#3aa66b", "#c25ad1"]
    for idx, (mint, symbol, name, grad_ago, mentions) in enumerate(tokens):
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
            f'<circle cx="32" cy="32" r="32" fill="{colors[idx % len(colors)]}"/>'
            f'<text x="32" y="40" font-size="26" text-anchor="middle" fill="white" '
            f'font-family="sans-serif">{symbol[0]}</text></svg>'
        )
        import urllib.parse
        image_uri = "data:image/svg+xml," + urllib.parse.quote(svg)
        db.record_graduation(mint, symbol, name, "{}", when=now - grad_ago, image_uri=image_uri)
        for i, mention in enumerate(mentions):
            # Most entries are (ago, author, text); a few carry a trailing
            # True to simulate a bot-shaped account for the preview.
            if len(mention) == 4:
                ago, author, text, is_bot = mention
            else:
                ago, author, text = mention
                is_bot = False
            db.record_mention(
                tweet_id=f"{mint}-{i}",
                mint=mint,
                author=author,
                text=text,
                posted_at=now - ago,
                matched_query="demo",
                author_followers=0 if is_bot else 40,
                account_age_days=2 if is_bot else 250,
                likely_bot=is_bot,
            )


seed_demo_data()

from dashboard import app  # noqa: E402  (must come after env vars are set above)

if __name__ == "__main__":
    print("Preview mode -- this is sample data, not live. Opening your browser...")
    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8787")).start()
    app.run(host="0.0.0.0", port=8787, debug=False, use_reloader=False)
