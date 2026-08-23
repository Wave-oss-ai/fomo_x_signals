"""
Local web dashboard for signals.db -- run this alongside (or instead of
watching the console output of) main.py to see graduated tokens and their X
attention in a browser, auto-refreshing every few seconds.

    python dashboard.py

Then open http://localhost:8787

This reads the same signals.db that main.py writes to, so you can run both
at once: `python main.py` in one terminal collecting data, `python
dashboard.py` in another to watch it.
"""
import os

from flask import Flask, jsonify, render_template_string

import db
import correlate

app = Flask(__name__)
DEMO_MODE = os.environ.get("FOMO_DEMO_MODE") == "1"

PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>fomo_x_signals dashboard</title>
<style>
  :root {
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page:           #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --muted:          #898781;
    --grid:           #e1e0d9;
    --border:         rgba(11,11,11,0.10);
    --series-1:       #2a78d6;
    --critical:       #d03b3b;
    --critical-bg:    #fbeceb;
    --warning:        #a66a00;
    --warning-bg:     #fdf1d9;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) {
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page:           #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --muted:          #898781;
      --grid:           #2c2c2a;
      --border:         rgba(255,255,255,0.10);
      --series-1:       #3987e5;
      --critical:       #e66767;
      --critical-bg:    #3a201f;
      --warning:        #c98500;
      --warning-bg:     #3a2d0d;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page:           #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --muted:          #898781;
    --grid:           #2c2c2a;
    --border:         rgba(255,255,255,0.10);
    --series-1:       #3987e5;
    --critical:       #e66767;
    --critical-bg:    #3a201f;
    --warning:        #c98500;
    --warning-bg:     #3a2d0d;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--page);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 32px 24px 64px;
  }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: var(--text-secondary); font-size: 13px; margin: 0 0 28px; }

  .stats { display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }
  .stat-tile {
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 18px;
    min-width: 140px;
  }
  .stat-tile .value { font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .stat-tile .label { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }

  .tabs { display: flex; gap: 6px; margin-bottom: 8px; }
  .tab {
    font: inherit; font-size: 13px; font-weight: 500; cursor: pointer;
    color: var(--text-secondary); background: transparent;
    border: 1px solid var(--border); border-radius: 999px;
    padding: 6px 14px;
  }
  .tab:hover { color: var(--text-primary); }
  .tab.active { color: var(--text-primary); background: var(--surface-1); border-color: var(--series-1); }
  .tab-note { color: var(--muted); font-size: 12px; margin: 0 0 16px; }

  table { width: 100%; border-collapse: collapse; background: var(--surface-1);
          border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  th, td { text-align: left; padding: 10px 14px; font-size: 13px; border-bottom: 1px solid var(--grid); }
  th { color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; }
  tbody tr:last-child td { border-bottom: none; }
  td.num { font-variant-numeric: tabular-nums; }
  td.mint { color: var(--muted); font-size: 11px; font-family: ui-monospace, monospace; }

  .token-name { font-weight: 500; }
  .token-symbol { color: var(--muted); font-size: 11px; margin-top: 1px; }
  .bot-note { color: var(--muted); font-size: 10px; font-weight: 400; white-space: nowrap; }

  .badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
    font-variant-numeric: tabular-nums;
  }
  .badge.warning { color: var(--warning); background: var(--warning-bg); }
  .badge.muted { color: var(--muted); background: transparent; }
  .badge.critical { color: var(--critical); background: var(--critical-bg); }
  .badge.normal { color: var(--muted); }

  .empty { color: var(--text-secondary); font-size: 13px; padding: 24px; text-align: center; }

  .demo-banner {
    display: flex; align-items: center; gap: 8px;
    background: var(--warning-bg); color: var(--warning);
    border-radius: 8px; padding: 10px 14px; font-size: 13px; font-weight: 500;
    margin-bottom: 20px;
  }
</style>
</head>
<body>
  <h1>fomo_x_signals</h1>
  <p class="sub">Solana pump.fun-style graduations, cross-referenced with X mentions. Refreshes every 5s.<br>
  Attention Score (0-100) measures social buzz -- mention volume, how many different people are posting, and how fast it's picking up -- not price. Accounts that look automated (brand-new + high-volume, zero followers + mass-posting, or a generated-looking handle) are filtered out before scoring, and the count still tells you how many got excluded. This is a heuristic, not certainty, and can't tell a genuine trend from a coordinated pump. Not financial advice.</p>

  {% if demo %}
  <div class="demo-banner">&#9888; Preview mode -- this is sample data, not live. Add your API keys and run <code>start.bat</code> for the real thing.</div>
  {% endif %}

  <div class="stats" id="stats"></div>

  <div class="tabs" id="tabs">
    <button class="tab active" data-filter="all">All</button>
    <button class="tab" data-filter="Broader interest">Broader Interest</button>
    <button class="tab" data-filter="Concentrated activity">Concentrated Activity</button>
  </div>
  <p class="tab-note">Based on how many different people are posting vs. one or two accounts repeating themselves -- not a safety rating. Every token here carries real risk either way.</p>

  <div id="table-wrap"></div>

<script>
function timeAgo(unixSeconds) {
  if (!unixSeconds) return '-';
  const diff = Math.max(0, (Date.now() / 1000) - unixSeconds);
  if (diff < 90) return Math.round(diff) + 's ago';
  if (diff < 5400) return Math.round(diff / 60) + 'm ago';
  return Math.round(diff / 3600) + 'h ago';
}

function fmtLead(leadSeconds) {
  if (leadSeconds === null || leadSeconds === undefined) return '-';
  const abs = Math.round(Math.abs(leadSeconds));
  return leadSeconds > 0 ? `+${abs}s early` : `${abs}s after`;
}

function scoreBadge(score, band) {
  const cls = band === 'Very High' ? 'critical' : band === 'High' ? 'warning' : 'muted';
  return `<span class="badge ${cls}">${score} &middot; ${band}</span>`;
}

let latestRows = [];
let activeFilter = 'all';

function renderTable() {
  const wrap = document.getElementById('table-wrap');

  if (!latestRows.length) {
    wrap.innerHTML = `<div class="empty">No graduations yet. Run <code>python main.py</code> to start collecting data.</div>`;
    return;
  }

  const filtered = activeFilter === 'all'
    ? latestRows
    : latestRows.filter(r => r.pattern === activeFilter);

  if (!filtered.length) {
    wrap.innerHTML = `<div class="empty">Nothing in this category yet.</div>`;
    return;
  }

  const rows = filtered.map(r => `
    <tr>
      <td>
        <div class="token-name">${r.name || r.symbol || '?'}</div>
        <div class="token-symbol">${r.symbol ? '$' + r.symbol : ''}</div>
      </td>
      <td>${scoreBadge(r.score, r.band)}</td>
      <td>${r.pattern}</td>
      <td>${timeAgo(r.graduated_at)}</td>
      <td class="num">${r.mention_count}${r.bot_mentions_excluded ? `<div class="bot-note">${r.bot_mentions_excluded} bot-like excluded</div>` : ''}</td>
      <td class="num">${r.distinct_authors}</td>
      <td>${timeAgo(r.first_mention_at)}</td>
      <td>${fmtLead(r.lead_seconds)}</td>
      <td class="mint">${r.mint}</td>
    </tr>
  `).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr>
        <th>Token</th><th>Attention Score</th><th>Pattern</th><th>Graduated</th><th>Mentions</th><th>Authors</th><th>First Mention</th><th>Lead / Lag</th><th>Mint</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

document.getElementById('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  activeFilter = btn.dataset.filter;
  renderTable();
});

async function refresh() {
  let data;
  try {
    const res = await fetch('/api/data');
    data = await res.json();
  } catch (e) {
    document.getElementById('table-wrap').innerHTML =
      `<div class="empty">Couldn't reach the dashboard API -- is dashboard.py still running?</div>`;
    return;
  }

  document.getElementById('stats').innerHTML = `
    <div class="stat-tile"><div class="value">${data.stats.tracked}</div><div class="label">Graduations tracked</div></div>
    <div class="stat-tile"><div class="value">${data.stats.total_mentions}</div><div class="label">X mentions collected</div></div>
    <div class="stat-tile"><div class="value">${data.stats.high_attention}</div><div class="label">High-attention alerts</div></div>
  `;

  latestRows = data.rows;
  renderTable();
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE, demo=DEMO_MODE)


@app.after_request
def add_cors_headers(response):
    # Lets a page embedded on a different website (e.g. pasted into a
    # website builder as an "embed HTML" block) fetch this API directly.
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/api/data")
def api_data():
    graduations = db.recent_graduations()
    rows = []
    total_mentions = 0
    high_attention = 0

    for g in graduations:
        stats = correlate.attention_score(g["mint"])
        total_mentions += stats["count"]
        is_high = stats["score"] >= 50  # "High" band or above
        if is_high:
            high_attention += 1
        rows.append({
            "symbol": g["symbol"],
            "name": g["name"],
            "mint": g["mint"],
            "graduated_at": g["graduated_at"],
            "mention_count": stats["count"],
            "distinct_authors": stats["distinct_authors"],
            "first_mention_at": stats["first_mention_at"],
            "lead_seconds": stats["lead_seconds"],
            "score": stats["score"],
            "band": stats["band"],
            "pattern": stats["pattern"],
            "bot_mentions_excluded": stats["bot_mentions_excluded"],
            "high_attention": is_high,
        })

    rows.sort(key=lambda r: r["score"], reverse=True)

    return jsonify({
        "stats": {
            "tracked": len(graduations),
            "total_mentions": total_mentions,
            "high_attention": high_attention,
        },
        "rows": rows,
    })


if __name__ == "__main__":
    db.init_db()
    print("Dashboard running at http://localhost:8787")
    app.run(host="0.0.0.0", port=8787, debug=False)
