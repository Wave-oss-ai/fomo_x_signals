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
from config import MIN_MARKET_CAP_USD, HIGH_PRIORITY_VELOCITY_PCT

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
    --positive:       #1a8a4a;
    --positive-bg:    #e8f5ec;
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
      --positive:       #4ec883;
      --positive-bg:    #16321f;
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
    --positive:       #4ec883;
    --positive-bg:    #16321f;
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
  tr.high-priority { background: var(--critical-bg); }
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
  .badge.positive { color: var(--positive); background: var(--positive-bg); }

  .mint-cell { display: flex; align-items: center; gap: 6px; }
  .copy-btn {
    font: inherit; font-size: 10px; cursor: pointer; white-space: nowrap;
    color: var(--muted); background: transparent; border: 1px solid var(--border);
    border-radius: 6px; padding: 2px 6px;
  }
  .copy-btn:hover { color: var(--text-primary); border-color: var(--series-1); }

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
  <p class="sub">Solana pump.fun-style graduations, cross-referenced with X mentions. Refreshes every 5s. &#128293; High Priority = moving right now, not a prediction it keeps moving. Heuristics, not certainty -- not financial advice.</p>

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

function fmtUsd(n) {
  if (n === null || n === undefined) return '-';
  if (n >= 1000000) return '$' + (n / 1000000).toFixed(2) + 'M';
  if (n >= 1000) return '$' + (n / 1000).toFixed(1) + 'K';
  return '$' + n.toFixed(0);
}

function fmtPct(n) {
  if (n === null || n === undefined) return '-';
  const cls = n > 0 ? 'positive' : n < 0 ? 'critical' : 'normal';
  const sign = n > 0 ? '+' : '';
  return `<span class="badge ${cls}">${sign}${n.toFixed(1)}%</span>`;
}

function copyMint(mint, el) {
  navigator.clipboard.writeText(mint).then(() => {
    const original = el.textContent;
    el.textContent = 'Copied!';
    setTimeout(() => { el.textContent = original; }, 1200);
  });
}
window.copyMint = copyMint;

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

  const rows = filtered.map((r, i) => `
    <tr class="${r.is_high_priority ? 'high-priority' : ''}">
      <td>
        <div class="token-name">${r.is_high_priority ? '&#128293; ' : ''}${r.name || r.symbol || '?'}</div>
        <div class="token-symbol">${r.symbol ? '$' + r.symbol : ''}</div>
      </td>
      <td>${scoreBadge(r.score, r.band)}</td>
      <td>${r.pattern}</td>
      <td>${timeAgo(r.graduated_at)}</td>
      <td class="num">${fmtUsd(r.market_cap_usd)}</td>
      <td class="num">${fmtPct(r.pct_change)}</td>
      <td class="num">${r.mention_count}${r.bot_mentions_excluded ? `<div class="bot-note">${r.bot_mentions_excluded} bot-like excluded</div>` : ''}</td>
      <td class="num">${r.distinct_authors}</td>
      <td>${timeAgo(r.first_mention_at)}</td>
      <td>${fmtLead(r.lead_seconds)}</td>
      <td class="mint">
        <div class="mint-cell">
          <span>${r.mint}</span>
          <button class="copy-btn" onclick="copyMint('${r.mint}', this)">Copy</button>
        </div>
      </td>
    </tr>
  `).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr>
        <th>Token</th><th>Attention Score</th><th>Pattern</th><th>Graduated</th><th>Market Cap</th><th>% Since Grad</th><th>Mentions</th><th>Authors</th><th>First Mention</th><th>Lead / Lag</th><th>Mint</th>
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
    <div class="stat-tile"><div class="value">${data.stats.high_priority}</div><div class="label">&#128293; High priority (big movers)</div></div>
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

    for g in graduations:
        market_cap_usd = g["market_cap_usd"]
        if market_cap_usd is not None and market_cap_usd < MIN_MARKET_CAP_USD:
            continue  # crashed/rugged -- not worth showing

        stats = correlate.attention_score(g["mint"])
        grad_market_cap_usd = g["graduation_market_cap_usd"]
        pct_change = None
        if market_cap_usd is not None and grad_market_cap_usd:
            pct_change = (market_cap_usd - grad_market_cap_usd) / grad_market_cap_usd * 100

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
            "high_attention": stats["score"] >= 50,  # "High" band or above
            "market_cap_usd": market_cap_usd,
            "pct_change": pct_change,
            "recent_velocity_pct": g["recent_velocity_pct"],
            "is_high_priority": g["recent_velocity_pct"] is not None and g["recent_velocity_pct"] >= HIGH_PRIORITY_VELOCITY_PCT,
        })

    # pump.fun lets anyone reuse a popular name AND/OR ticker for a
    # brand-new, unrelated mint, so copycats can share just the name, just
    # the symbol, or both. Union-find groups any tokens connected by either
    # matching field, then we keep only the highest-market-cap mint per
    # group so the list doesn't repeat what looks like "the same" token.
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for key_fn in (lambda r: r["name"], lambda r: r["symbol"]):
        first_seen = {}
        for i, r in enumerate(rows):
            key = key_fn(r)
            if not key:
                continue
            key = key.lower().strip()
            if key in first_seen:
                union(first_seen[key], i)
            else:
                first_seen[key] = i

    best_by_group = {}
    for i, r in enumerate(rows):
        root = find(i)
        existing = best_by_group.get(root)
        if existing is None or (r["market_cap_usd"] or 0) > (existing["market_cap_usd"] or 0):
            best_by_group[root] = r
    rows = list(best_by_group.values())

    # High-priority (actively pushing right now) tokens float to the very
    # top; within that, newest graduations first so fresh tokens don't get
    # buried under older ones as the list grows.
    rows.sort(key=lambda r: (r["is_high_priority"], r["graduated_at"]), reverse=True)

    total_mentions = sum(r["mention_count"] for r in rows)
    high_attention = sum(1 for r in rows if r["high_attention"])
    high_priority = sum(1 for r in rows if r["is_high_priority"])

    return jsonify({
        "stats": {
            "tracked": len(rows),
            "total_mentions": total_mentions,
            "high_attention": high_attention,
            "high_priority": high_priority,
        },
        "rows": rows,
    })


if __name__ == "__main__":
    db.init_db()
    print("Dashboard running at http://localhost:8787")
    app.run(host="0.0.0.0", port=8787, debug=False)
