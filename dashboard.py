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
import re

from flask import Flask, jsonify, render_template_string

import db
import correlate
import graduation_watcher
from config import (
    MIN_MARKET_CAP_USD, HIGH_PRIORITY_VELOCITY_PCT, PRE_MARKET_WATCH_WINDOW_MIN,
    CREATOR_SUCCESS_RATE, MIN_CREATOR_COINS,
)

def dedupe_copycats(rows):
    """pump.fun lets anyone reuse a popular name AND/OR ticker for a
    brand-new, unrelated mint, so copycats can share just the name, just the
    symbol, or both -- and often spam the *exact same* name repeatedly
    within seconds (the same deployer relaunching after a rug), or a
    prefix/suffix variation of a popular name ("Pistacio" / "Baby Pistacio").
    Union-find groups any rows connected by an exact name/symbol match or by
    one normalized name being contained in another, then keeps only the
    highest-market-cap row per group so the list doesn't repeat what looks
    like "the same" token."""
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

    def normalize(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    norm_names = [normalize(r["name"]) for r in rows]
    for i in range(len(rows)):
        a = norm_names[i]
        if len(a) < 4:
            continue
        for j in range(i + 1, len(rows)):
            b = norm_names[j]
            if len(b) < 4:
                continue
            if a in b or b in a:
                union(i, j)

    best_by_group = {}
    for i, r in enumerate(rows):
        root = find(i)
        existing = best_by_group.get(root)
        if existing is None or (r["market_cap_usd"] or 0) > (existing["market_cap_usd"] or 0):
            best_by_group[root] = r
    return list(best_by_group.values())


app = Flask(__name__)
DEMO_MODE = os.environ.get("FOMO_DEMO_MODE") == "1"


def recent_mentions(mint, limit=12):
    """The actual X posts behind a token's Attention Score, newest first --
    lets you sanity-check the score instead of just trusting a number."""
    mentions = db.mentions_for(mint)
    mentions = sorted(mentions, key=lambda m: m["posted_at"], reverse=True)[:limit]
    return [
        {
            "author": m["author"],
            "text": m["text"],
            "posted_at": m["posted_at"],
            "tweet_id": m["tweet_id"],
            "likely_bot": bool(m["likely_bot"]),
        }
        for m in mentions
    ]

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

  .controls-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; margin-bottom: 10px; flex-wrap: wrap;
  }
  .search-input {
    font: inherit; font-size: 13px; padding: 6px 14px; border-radius: 999px;
    border: 1px solid var(--border); background: var(--surface-1);
    color: var(--text-primary); min-width: 240px;
  }
  .search-input:focus { outline: none; border-color: var(--series-1); }
  .search-input::placeholder { color: var(--muted); }
  .last-updated { color: var(--muted); font-size: 12px; white-space: nowrap; }

  .token-cell { display: flex; align-items: center; gap: 8px; }
  .token-avatar {
    width: 28px; height: 28px; border-radius: 50%; object-fit: cover;
    flex-shrink: 0; background: var(--grid); border: 1px solid var(--border);
  }
  .token-avatar.placeholder {
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 600; color: var(--muted);
  }

  .token-links { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
  .token-links a {
    font-size: 10px; color: var(--muted); text-decoration: none;
    border: 1px solid var(--border); border-radius: 5px; padding: 1px 5px;
  }
  .token-links a:hover { color: var(--series-1); border-color: var(--series-1); }

  th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
  th.sortable:hover { color: var(--text-primary); }
  th.sortable .arrow { opacity: 0.45; margin-left: 3px; font-size: 9px; }
  th.sortable.active .arrow { opacity: 1; color: var(--series-1); }

  tr.token-row { cursor: pointer; }
  tr.token-row:hover td { background: var(--page); }
  tr.detail-row td { background: var(--page); padding: 0; }
  .detail-panel { padding: 10px 16px; max-height: 260px; overflow-y: auto; }
  .detail-empty { color: var(--muted); font-size: 12px; padding: 6px 0; }
  .mention-item { padding: 7px 0; border-bottom: 1px solid var(--grid); font-size: 12px; }
  .mention-item:last-child { border-bottom: none; }
  .mention-head {
    display: flex; gap: 8px; align-items: baseline; color: var(--muted);
    font-size: 11px; margin-bottom: 2px; flex-wrap: wrap;
  }
  .mention-head a { color: var(--series-1); text-decoration: none; }
  .mention-head a:hover { text-decoration: underline; }
  .mention-text { color: var(--text-primary); }
</style>
</head>
<body>
  <h1>fomo_x_signals</h1>
  <p class="sub">Solana pump.fun-style graduations, cross-referenced with X mentions. Refreshes every 2s. &#128293; High Priority = moving right now, not a prediction it keeps moving. Heuristics, not certainty -- not financial advice.</p>

  {% if demo %}
  <div class="demo-banner">&#9888; Preview mode -- this is sample data, not live. Add your API keys and run <code>start.bat</code> for the real thing.</div>
  {% endif %}

  <div class="stats" id="stats"></div>

  <div class="controls-row">
    <input id="search-input" class="search-input" type="text" placeholder="Search name, symbol, or mint...">
    <span class="last-updated" id="last-updated"></span>
  </div>

  <div class="tabs" id="view-tabs">
    <button class="tab active" data-view="graduated">Graduated</button>
    <button class="tab" data-view="premarket">&#128293; Pre-Market Hype</button>
    <button class="tab" data-view="prelaunch">&#128302; Pre-Launch Chatter</button>
  </div>

  <div class="tabs" id="tabs">
    <button class="tab active" data-filter="all">All</button>
    <button class="tab" data-filter="Broader interest">Broader Interest</button>
    <button class="tab" data-filter="Concentrated activity">Concentrated Activity</button>
    <button class="tab" data-filter="Proven creator">&#127942; Proven Creators</button>
  </div>
  <p class="tab-note" id="tab-note">Based on how many different people are posting vs. one or two accounts repeating themselves -- not a safety rating. Every token here carries real risk either way. &#127942; Proven Creator = this wallet's launched 2+ coins before and most of them graduated -- past behavior, not a guarantee this one does too.</p>

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

function creatorBadge(r) {
  if (!r.creator_total_coins) return `<span class="badge muted">Unknown</span>`;
  const cls = r.is_proven_creator ? 'positive' : 'muted';
  const label = r.is_proven_creator ? '&#127942; ' : '';
  return `<span class="badge ${cls}">${label}${r.creator_graduated_coins}/${r.creator_total_coins} graduated</span>`;
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
let latestPreMarketRows = [];
let latestPreLaunchRows = [];
let activeFilter = 'all';
let activeView = 'graduated';
let searchQuery = '';
let sortKey = null;
let sortDir = 'desc';
let expandedMints = new Set();
let lastUpdated = null;

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s || '';
  return div.innerHTML;
}

function avatarFallback(img, label) {
  const div = document.createElement('div');
  div.className = 'token-avatar placeholder';
  div.textContent = label;
  img.replaceWith(div);
}
window.avatarFallback = avatarFallback;

function tokenAvatar(r) {
  const label = escapeHtml((r.symbol || r.name || '?').charAt(0).toUpperCase());
  if (!r.image_uri) return `<div class="token-avatar placeholder">${label}</div>`;
  return `<img class="token-avatar" src="${escapeHtml(r.image_uri)}" alt="" loading="lazy" onerror="avatarFallback(this,'${label}')">`;
}

function externalLinks(mint, symbol) {
  const q = encodeURIComponent(symbol ? '$' + symbol : mint);
  return `<div class="token-links" onclick="event.stopPropagation()">
    <a href="https://pump.fun/coin/${mint}" target="_blank" rel="noopener">pump.fun</a>
    <a href="https://dexscreener.com/solana/${mint}" target="_blank" rel="noopener">chart</a>
    <a href="https://solscan.io/token/${mint}" target="_blank" rel="noopener">solscan</a>
    <a href="https://x.com/search?q=${q}&src=typed_query" target="_blank" rel="noopener">X search</a>
  </div>`;
}

function sortableTh(label, key) {
  const active = sortKey === key;
  const arrow = active ? (sortDir === 'asc' ? '&#9650;' : '&#9660;') : '&#8597;';
  return `<th class="sortable ${active ? 'active' : ''}" onclick="onSortClick('${key}')">${label} <span class="arrow">${arrow}</span></th>`;
}

function onSortClick(key) {
  if (sortKey === key) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey = key;
    sortDir = 'desc';
  }
  renderTable();
}
window.onSortClick = onSortClick;

function applySort(rows) {
  if (!sortKey) return rows;
  return [...rows].sort((a, b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (av === null || av === undefined) av = -Infinity;
    if (bv === null || bv === undefined) bv = -Infinity;
    if (av < bv) return sortDir === 'asc' ? -1 : 1;
    if (av > bv) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });
}

function matchesSearch(r) {
  if (!searchQuery) return true;
  const hay = [r.name, r.symbol, r.mint, r.author, r.text].filter(Boolean).join(' ').toLowerCase();
  return hay.includes(searchQuery);
}

function toggleExpand(mint) {
  if (expandedMints.has(mint)) expandedMints.delete(mint); else expandedMints.add(mint);
  renderTable();
}
window.toggleExpand = toggleExpand;

function renderDetailPanel(r) {
  const mentions = r.mentions || [];
  if (!mentions.length) {
    return `<div class="detail-panel"><div class="detail-empty">No individual X mentions stored for this token yet -- the Attention Score above is 0 or based on data that's since aged out.</div></div>`;
  }
  const items = mentions.map(m => `
    <div class="mention-item">
      <div class="mention-head">
        <span>@${escapeHtml(m.author || '?')}</span>
        ${m.likely_bot ? '<span class="bot-note">(bot-like, excluded from score)</span>' : ''}
        <span>${timeAgo(m.posted_at)}</span>
        ${m.tweet_id ? `<a href="https://x.com/i/status/${m.tweet_id}" target="_blank" rel="noopener">view post &#8599;</a>` : ''}
      </div>
      <div class="mention-text">${escapeHtml(m.text)}</div>
    </div>
  `).join('');
  return `<div class="detail-panel">${items}</div>`;
}

function updateLastUpdatedText() {
  const el = document.getElementById('last-updated');
  if (!el || !lastUpdated) return;
  const secs = Math.round((Date.now() - lastUpdated) / 1000);
  el.textContent = secs <= 1 ? 'Updated just now' : `Updated ${secs}s ago`;
}
setInterval(updateLastUpdatedText, 1000);

function renderPreLaunchTable() {
  const wrap = document.getElementById('table-wrap');

  if (!latestPreLaunchRows.length) {
    wrap.innerHTML = `<div class="empty">No pre-launch chatter matched yet -- watching X for phrases/accounts set in PRE_LAUNCH_KEYWORDS / PRE_LAUNCH_ACCOUNTS (config.py). Not tied to any specific token since none exists on-chain yet.</div>`;
    return;
  }

  const filtered = latestPreLaunchRows.filter(matchesSearch);
  if (!filtered.length) {
    wrap.innerHTML = `<div class="empty">No pre-launch chatter matches your search.</div>`;
    return;
  }

  const rows = filtered.map(r => `
    <tr>
      <td>@${escapeHtml(r.author || '?')}${r.likely_bot ? ' <span class="bot-note">(bot-like)</span>' : ''}</td>
      <td>${escapeHtml(r.text)}</td>
      <td>${timeAgo(r.posted_at)}</td>
    </tr>
  `).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr><th>Author</th><th>Post</th><th>Posted</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderPreMarketTable() {
  const wrap = document.getElementById('table-wrap');

  if (!latestPreMarketRows.length) {
    wrap.innerHTML = `<div class="empty">No pre-market hype detected yet -- watching new pump.fun launches (not yet graduated) for early X mentions.</div>`;
    return;
  }

  const filtered = applySort(latestPreMarketRows.filter(matchesSearch));
  if (!filtered.length) {
    wrap.innerHTML = `<div class="empty">Nothing matches your search.</div>`;
    return;
  }

  const rows = filtered.map(r => {
    const isOpen = expandedMints.has(r.mint);
    const mainRow = `
    <tr class="token-row" onclick="toggleExpand('${r.mint}')">
      <td>
        <div class="token-cell">
          ${tokenAvatar(r)}
          <div>
            <div class="token-name">${escapeHtml(r.name || r.symbol || '?')}</div>
            <div class="token-symbol">${r.symbol ? '$' + escapeHtml(r.symbol) : ''}</div>
          </div>
        </div>
      </td>
      <td>${scoreBadge(r.score, r.band)}</td>
      <td>${r.pattern}</td>
      <td>${timeAgo(r.created_at)}</td>
      <td class="num">${fmtUsd(r.market_cap_usd)}</td>
      <td class="num">${r.mention_count}${r.bot_mentions_excluded ? `<div class="bot-note">${r.bot_mentions_excluded} bot-like excluded</div>` : ''}</td>
      <td class="num">${r.distinct_authors}</td>
      <td>${timeAgo(r.first_mention_at)}</td>
      <td class="mint">
        <div class="mint-cell">
          <span>${r.mint}</span>
          <button class="copy-btn" onclick="event.stopPropagation(); copyMint('${r.mint}', this)">Copy</button>
        </div>
        ${externalLinks(r.mint, r.symbol)}
      </td>
    </tr>`;
    const detailRow = isOpen ? `<tr class="detail-row"><td colspan="9">${renderDetailPanel(r)}</td></tr>` : '';
    return mainRow + detailRow;
  }).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr>
        <th>Token</th>${sortableTh('Attention Score', 'score')}<th>Pattern</th>${sortableTh('Created', 'created_at')}${sortableTh('Market Cap', 'market_cap_usd')}${sortableTh('Mentions', 'mention_count')}${sortableTh('Authors', 'distinct_authors')}${sortableTh('First Mention', 'first_mention_at')}<th>Mint</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderTable() {
  if (activeView === 'premarket') {
    renderPreMarketTable();
    return;
  }
  if (activeView === 'prelaunch') {
    renderPreLaunchTable();
    return;
  }

  const wrap = document.getElementById('table-wrap');

  if (!latestRows.length) {
    wrap.innerHTML = `<div class="empty">No graduations yet. Run <code>python main.py</code> to start collecting data.</div>`;
    return;
  }

  let filtered = activeFilter === 'all'
    ? latestRows
    : activeFilter === 'Proven creator'
      ? latestRows.filter(r => r.is_proven_creator)
      : latestRows.filter(r => r.pattern === activeFilter);
  filtered = applySort(filtered.filter(matchesSearch));

  if (!filtered.length) {
    wrap.innerHTML = `<div class="empty">Nothing matches the current tab/search.</div>`;
    return;
  }

  const rows = filtered.map(r => {
    const isOpen = expandedMints.has(r.mint);
    const mainRow = `
    <tr class="token-row ${r.is_high_priority ? 'high-priority' : ''}" onclick="toggleExpand('${r.mint}')">
      <td>
        <div class="token-cell">
          ${tokenAvatar(r)}
          <div>
            <div class="token-name">${r.is_high_priority ? '&#128293; ' : ''}${escapeHtml(r.name || r.symbol || '?')}</div>
            <div class="token-symbol">${r.symbol ? '$' + escapeHtml(r.symbol) : ''}</div>
          </div>
        </div>
      </td>
      <td>${scoreBadge(r.score, r.band)}</td>
      <td>${r.pattern}</td>
      <td>${creatorBadge(r)}</td>
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
          <button class="copy-btn" onclick="event.stopPropagation(); copyMint('${r.mint}', this)">Copy</button>
        </div>
        ${externalLinks(r.mint, r.symbol)}
      </td>
    </tr>`;
    const detailRow = isOpen ? `<tr class="detail-row"><td colspan="11">${renderDetailPanel(r)}</td></tr>` : '';
    return mainRow + detailRow;
  }).join('');

  wrap.innerHTML = `
    <table>
      <thead><tr>
        <th>Token</th>${sortableTh('Attention Score', 'score')}<th>Pattern</th><th>Creator</th>${sortableTh('Graduated', 'graduated_at')}${sortableTh('Market Cap', 'market_cap_usd')}${sortableTh('% Since Grad', 'pct_change')}${sortableTh('Mentions', 'mention_count')}${sortableTh('Authors', 'distinct_authors')}${sortableTh('First Mention', 'first_mention_at')}${sortableTh('Lead / Lag', 'lead_seconds')}<th>Mint</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

document.getElementById('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  document.querySelectorAll('#tabs .tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  activeFilter = btn.dataset.filter;
  renderTable();
});

document.getElementById('view-tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  document.querySelectorAll('#view-tabs .tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  activeView = btn.dataset.view;
  sortKey = null;
  const showFilterTabs = activeView === 'graduated';
  document.getElementById('tabs').style.display = showFilterTabs ? 'flex' : 'none';
  document.getElementById('tab-note').style.display = showFilterTabs ? 'block' : 'none';
  renderTable();
});

document.getElementById('search-input').addEventListener('input', (e) => {
  searchQuery = e.target.value.trim().toLowerCase();
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

  lastUpdated = Date.now();
  updateLastUpdatedText();

  document.getElementById('stats').innerHTML = `
    <div class="stat-tile"><div class="value">${data.stats.tracked}</div><div class="label">Graduations tracked</div></div>
    <div class="stat-tile"><div class="value">${data.stats.total_mentions}</div><div class="label">X mentions collected</div></div>
    <div class="stat-tile"><div class="value">${data.stats.high_attention}</div><div class="label">High-attention alerts</div></div>
    <div class="stat-tile"><div class="value">${data.stats.high_priority}</div><div class="label">&#128293; High priority (big movers)</div></div>
    <div class="stat-tile"><div class="value">${data.stats.pre_market_hype}</div><div class="label">&#128293; Pre-market hype</div></div>
    <div class="stat-tile"><div class="value">${data.stats.pre_launch_signals}</div><div class="label">&#128302; Pre-launch chatter</div></div>
  `;

  latestRows = data.rows;
  latestPreMarketRows = data.pre_market_rows || [];
  latestPreLaunchRows = data.pre_launch_rows || [];
  renderTable();
}

refresh();
setInterval(refresh, 2000);
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

        creator_total = g["creator_total_coins"]
        creator_graduated = g["creator_graduated_coins"]
        is_proven_creator = (
            creator_total is not None and creator_total >= MIN_CREATOR_COINS
            and creator_graduated is not None and creator_graduated / creator_total > CREATOR_SUCCESS_RATE
        )

        rows.append({
            "symbol": g["symbol"],
            "name": g["name"],
            "mint": g["mint"],
            "image_uri": g["image_uri"],
            "graduated_at": g["graduated_at"],
            "creator": g["creator"],
            "creator_total_coins": creator_total,
            "creator_graduated_coins": creator_graduated,
            "is_proven_creator": is_proven_creator,
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
            "mentions": recent_mentions(g["mint"]),
        })

    rows = dedupe_copycats(rows)

    # High-priority (actively pushing right now) tokens float to the very
    # top; within that, newest graduations first so fresh tokens don't get
    # buried under older ones as the list grows.
    rows.sort(key=lambda r: (r["is_high_priority"], r["graduated_at"]), reverse=True)

    total_mentions = sum(r["mention_count"] for r in rows)
    high_attention = sum(1 for r in rows if r["high_attention"])
    high_priority = sum(1 for r in rows if r["is_high_priority"])

    # Pre-market: tokens that haven't graduated yet but are already showing
    # X hype. Only surface ones with at least one real mention -- otherwise
    # this would just be a list of every new pump.fun launch, which is noise.
    pre_market_rows = []
    for t in db.recent_new_tokens(since_minutes=PRE_MARKET_WATCH_WINDOW_MIN):
        stats = correlate.attention_score(t["mint"])
        if stats["count"] == 0:
            continue
        # Fetch once, reuse for both market cap and logo; cache the image
        # once we have it so we don't keep re-requesting it every refresh.
        _, _, market_cap_usd, image_uri, _ = graduation_watcher._fetch_metadata(t["mint"])
        image_uri = t["image_uri"] or image_uri
        if image_uri and not t["image_uri"]:
            db.update_new_token_image(t["mint"], image_uri)
        pre_market_rows.append({
            "symbol": t["symbol"],
            "name": t["name"],
            "mint": t["mint"],
            "image_uri": image_uri,
            "created_at": t["created_at"],
            "mention_count": stats["count"],
            "distinct_authors": stats["distinct_authors"],
            "first_mention_at": stats["first_mention_at"],
            "score": stats["score"],
            "band": stats["band"],
            "pattern": stats["pattern"],
            "bot_mentions_excluded": stats["bot_mentions_excluded"],
            # Pre-graduation tokens are still on the bonding curve, so these
            # market caps are typically tiny (often well under $5K) -- that's
            # expected, not a bug; MIN_MARKET_CAP_USD only filters graduated
            # tokens, not this pre-market list.
            "market_cap_usd": market_cap_usd,
            "mentions": recent_mentions(t["mint"]),
        })
    pre_market_rows = dedupe_copycats(pre_market_rows)
    pre_market_rows.sort(key=lambda r: r["score"], reverse=True)

    # Pre-launch: raw X chatter about tokens that haven't even launched
    # on-chain yet (matched by keyword/account, not a mint -- none exists).
    # Just the most recent signals, unscored, for a human to read.
    pre_launch_rows = db.recent_pre_launch_signals(since_minutes=24 * 60)[:50]

    return jsonify({
        "stats": {
            "tracked": len(rows),
            "total_mentions": total_mentions,
            "high_attention": high_attention,
            "high_priority": high_priority,
            "pre_market_hype": len(pre_market_rows),
            "pre_launch_signals": len(pre_launch_rows),
        },
        "rows": rows,
        "pre_market_rows": pre_market_rows,
        "pre_launch_rows": pre_launch_rows,
    })


if __name__ == "__main__":
    db.init_db()
    print("Dashboard running at http://localhost:8787")
    app.run(host="0.0.0.0", port=8787, debug=False)
