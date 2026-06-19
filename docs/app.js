/* ── ETF Rotation Radar — Frontend Logic ──────────────────── */

let DATA = null;
let sortCol = "percentile_rank";
let sortDir = -1; // descending
let lastScreenerSorted = []; // последно показаните редове (за CSV export)

// ── Tab Navigation ─────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
  });
});

// ── Load Data ──────────────────────────────────────────────
async function loadData() {
  try {
    const resp = await fetch("data.json?v=" + Date.now());
    DATA = await resp.json();
    init();
  } catch (e) {
    document.getElementById("as-of-label").textContent = "Error loading data";
    console.error(e);
  }
}

function init() {
  document.getElementById("as-of-label").textContent = "As of: " + DATA.as_of;

  // Populate category filters
  const cats = DATA.categories || [];
  ["cat-filter", "screener-cat-filter", "rs-cat-filter"].forEach(id => {
    const sel = document.getElementById(id);
    cats.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", renderAll);
  });

  renderBarometer();
  renderMacro();
  renderMovers();
  renderHeatstrip();

  document.getElementById("window-filter").addEventListener("change", renderAll);
  document.getElementById("screener-sort").addEventListener("change", () => {
    sortCol = document.getElementById("screener-sort").value;
    renderScreener();
  });
  document.getElementById("rs-signal-filter").addEventListener("change", renderRS);
  document.getElementById("btn-export-csv").addEventListener("click", exportScreenerCSV);

  // Table header sort
  document.querySelectorAll("th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (sortCol === col) { sortDir *= -1; } else { sortCol = col; sortDir = -1; }
      document.getElementById("screener-sort").value = col;
      renderScreener();
    });
  });

  renderAll();
}

function renderAll() {
  renderRadar();
  renderScreener();
  renderRS();
  renderHeatmap();
}

// ── Helpers ────────────────────────────────────────────────
function fmtPct(v, decimals = 1) {
  if (v == null) return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  const cls = n > 0 ? "positive" : n < 0 ? "negative" : "neutral";
  return `<span class="${cls}">${n >= 0 ? "+" : ""}${n.toFixed(decimals)}%</span>`;
}
function fmtNum(v, decimals = 2) {
  if (v == null) return "—";
  const n = parseFloat(v);
  return isNaN(n) ? "—" : n.toFixed(decimals);
}
function fmtAUM(v) {
  if (v == null) return "—";
  const n = parseFloat(v) / 1_000_000_000;
  return isNaN(n) ? "—" : n.toFixed(1) + "B";
}
function fmtDollarVol(v, flag) {
  if (v == null) return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  const txt = n >= 1e9 ? (n / 1e9).toFixed(1) + "B"
            : n >= 1e6 ? (n / 1e6).toFixed(0) + "M"
            : (n / 1e3).toFixed(0) + "K";
  const cls = flag === "thin" ? "negative" : "neutral";
  return `<span class="${cls}">${txt}</span>`;
}
function fmtFlow(pct, dollars, dir, windowDays) {
  // Нетен поток за мащаб+посока (груба оценка). "—" докато историята не стигне.
  if (pct == null) return `<span style="color:var(--text-muted)">—</span>`;
  const p = parseFloat(pct);
  if (isNaN(p)) return `<span style="color:var(--text-muted)">—</span>`;
  const cls = p > 0 ? "positive" : p < 0 ? "negative" : "neutral";
  const arrow = p > 0 ? "▲" : p < 0 ? "▼" : "·";
  let dTxt = "";
  if (dollars != null && !isNaN(parseFloat(dollars))) {
    const n = Math.abs(parseFloat(dollars));
    dTxt = n >= 1e9 ? "$" + (n / 1e9).toFixed(1) + "B"
         : n >= 1e6 ? "$" + (n / 1e6).toFixed(0) + "M"
         : "$" + (n / 1e3).toFixed(0) + "K";
  }
  const tip = `${dir === "in" ? "приток" : dir === "out" ? "отток" : "плоско"} ${dTxt}` +
              (windowDays != null ? ` за ~${windowDays}д` : "");
  return `<span class="${cls}" title="${tip}">${arrow}${Math.abs(p).toFixed(1)}%</span>`;
}
function filteredByCategory(catSelectId) {
  const cat = document.getElementById(catSelectId).value;
  return cat === "all" ? DATA.etfs : DATA.etfs.filter(e => e.category === cat);
}

// ── Sparkline (inline SVG, 2г седмично-децимиран Close) ─────
// „Формата на тренда" до всеки ранг. Зелено ако последното ≥ първото, иначе червено.
function sparkline(data) {
  if (!Array.isArray(data) || data.length < 2) return "";
  const w = 60, h = 16, n = data.length;
  const min = Math.min(...data), max = Math.max(...data), range = (max - min) || 1;
  const pts = data.map((v, i) =>
    `${(i / (n - 1) * w).toFixed(1)},${(h - (v - min) / range * h).toFixed(1)}`).join(" ");
  const up = data[n - 1] >= data[0];
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" `
    + `preserveAspectRatio="none" aria-hidden="true">`
    + `<polyline points="${pts}" fill="none" stroke="${up ? 'var(--green)' : 'var(--red)'}" `
    + `stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

// ── CSV Export (Screener) ──────────────────────────────────
// Изнася ТЕКУЩИЯ изглед (същия филтър + сортиране като таблицата), сурови числа —
// чист handoff към публикационния pipeline. Client-side, без зависимости.
const EXPORT_COLS = [
  ["ticker", "Ticker"], ["name", "Name"], ["category", "Category"],
  ["percentile_rank", "Rank%"], ["ret_1m", "Ret1M%"], ["ret_3m", "Ret3M%"],
  ["ret_12m", "Ret12M%"], ["sharpe_12m", "Sharpe (rf=0)"], ["max_dd_12m", "MaxDD%"],
  ["dist_52w_high", "vs52wH%"], ["drawdown_now", "DDnow%"], ["atr_pct", "ATR%"],
  ["stop_distance_pct", "Stop%"], ["expense_ratio", "ExpRatio%"], ["yield", "Yield%"],
  ["pe_ratio", "PE"], ["aum", "AUM"], ["dollar_vol_20d", "DollarVol20d"],
  ["est_flow_pct", "Flow%"], ["beta_1y", "Beta1Y"], ["corr_1y", "Corr1Y"],
  ["conc_top10", "ConcTop10%"], ["cot_pctile", "COTpctile"], ["cot_net", "COTnet"],
];
function csvCell(v) {
  if (v == null) return "";
  const s = typeof v === "number"
    ? (Number.isInteger(v) ? String(v) : String(+v.toFixed(4)))
    : String(v);
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function exportScreenerCSV() {
  const rows = lastScreenerSorted.length ? lastScreenerSorted
    : filteredByCategory("screener-cat-filter");
  const header = EXPORT_COLS.map(c => c[1]).join(",");
  const body = rows.map(e => EXPORT_COLS.map(c => csvCell(e[c[0]])).join(",")).join("\n");
  const blob = new Blob([header + "\n" + body], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `etf-screener-${DATA.as_of || "latest"}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Look-through tooltip (S18) — топ holdings + сектори за концентрацията ──
function concTooltip(e) {
  const parts = [];
  if (Array.isArray(e.holdings) && e.holdings.length) {
    parts.push("Топ holdings: " + e.holdings.map(h => `${h[0]} ${h[1]}%`).join(", "));
  }
  if (Array.isArray(e.sectors) && e.sectors.length) {
    parts.push("Сектори: " + e.sectors.map(s => `${s[0]} ${s[1]}%`).join(", "));
  }
  // escape за HTML title атрибута (кавички/амперсанд)
  return parts.join(" | ").replace(/"/g, "&quot;").replace(/&(?!quot;)/g, "&amp;");
}

// ── COT tooltip (S18) — net позициониране + детайли за percentile-а ──
function cotTooltip(e) {
  if (e.cot_pctile == null) return "";
  const dir = e.cot_net > 0 ? "нетно ДЪЛГИ" : e.cot_net < 0 ? "нетно КЪСИ" : "неутрални";
  const oi = e.cot_pct_oi != null ? ` (${e.cot_pct_oi}% от OI)` : "";
  const net = e.cot_net != null ? Math.abs(Number(e.cot_net)).toLocaleString("en-US") : "—";
  const t = `${e.cot_market || ""} · ${e.cot_kind || ""}: ${dir} ${net} контракта${oi}`
    + ` | percentile ${e.cot_pctile}% спрямо 3г${e.cot_date ? " · " + e.cot_date : ""}`;
  return t.replace(/"/g, "&quot;").replace(/&(?!quot;)/g, "&amp;");
}

// ── Movers since last week (Tier 3 UX) ─────────────────────
// Седмица-за-седмица ΔRank diff + ротация в челото. Независим от cat/window
// филтрите — рисува се веднъж в init() (като Барометъра/Макро стрипа).
function renderMovers() {
  const el = document.getElementById("movers-panel");
  if (!el) return;
  const m = DATA.movers;
  if (!m || !m.available) { el.style.display = "none"; return; }

  const moverRow = (r, dir) => {
    const cls = dir === "up" ? "positive" : "negative";
    const arrow = dir === "up" ? "▲" : "▼";
    const d = r.delta != null ? (r.delta > 0 ? "+" : "") + r.delta : "—";
    const ctx = (r.prev != null && r.now != null) ? `${r.prev}→${r.now}` : "";
    return `<div class="mv-row">
      <span class="mv-arrow ${cls}">${arrow}</span>
      <span class="q-ticker">${r.ticker}</span>
      <span class="q-cat-badge">${r.category || ""}</span>
      <span class="mv-name">${r.name || ""}</span>
      <span class="mv-ctx">${ctx}</span>
      <span class="mv-delta ${cls}">${d}</span>
    </div>`;
  };

  // Двата списъка — нагоре после надолу. По 8 на страна (праг ≥15 рядко дава повече).
  const upRows = m.up.slice(0, 8).map(r => moverRow(r, "up")).join("");
  const downRows = m.down.slice(0, 8).map(r => moverRow(r, "down")).join("");
  const moversHtml = (upRows + downRows) ||
    `<div class="mv-empty">Спокойна седмица — нито един ETF не мръдна с ${m.threshold}+ ранг пункта.</div>`;

  // Ротация в челото: pill-ове с tooltip (now = текущ momentum-перцентил 0–100).
  const pill = (r, dir) => {
    const cls = dir === "in" ? "positive" : "negative";
    const tip = dir === "in"
      ? `${r.name || r.ticker} · влезе в топ-${m.top_n} (ранг ${r.now}%)`
      : `${r.name || r.ticker} · напусна топ-${m.top_n} (ранг ${r.prev}%→${r.now}%)`;
    return `<span class="mv-pill ${cls}" title="${tip.replace(/"/g, "&quot;")}">`
      + `${r.ticker}<span class="mv-ctx">${r.now != null ? r.now : "—"}</span></span>`;
  };
  const entered = m.entered.length
    ? m.entered.map(r => pill(r, "in")).join("")
    : `<span class="mv-none">няма промяна</span>`;
  const left = m.left.length
    ? m.left.map(r => pill(r, "out")).join("")
    : `<span class="mv-none">няма промяна</span>`;

  el.innerHTML = `
    <div class="reg-head">
      <span class="reg-title">📊 Движения от ${m.prev_date}</span>
      <span class="reg-asof">седмица за седмица · |ΔRank| ≥ ${m.threshold}</span>
    </div>
    <div class="mv-grid">
      <div class="mv-col">
        <div class="mv-subhead">Най-големи движители</div>
        ${moversHtml}
      </div>
      <div class="mv-col">
        <div class="mv-subhead">Ротация в челото (топ-${m.top_n})</div>
        <div class="mv-rot"><span class="mv-rot-label positive">▲ влязоха</span><div class="mv-pills">${entered}</div></div>
        <div class="mv-rot"><span class="mv-rot-label negative">▼ напуснаха</span><div class="mv-pills">${left}</div></div>
      </div>
    </div>`;
  el.style.display = "block";
}

// ── Category-rotation heat-strip (Tier 3 UX) ───────────────
// 9 категории × 26 седмици; цвят по медиен абсолютен momentum-перцентил
// per категория per седмица. Дивержентна скала, центрирана на 50 (50=медианен
// ETF, 0/100=краища — всичко дефиниционно). Независим от cat/window филтрите —
// рисува се веднъж в init() (като Барометъра/Движенията).
function heatColor(v) {
  // v ∈ [0,100]. 50 → неутрално; <50 студено (синьо); >50 топло (червено).
  if (v == null || isNaN(v)) return "var(--bg3)";
  const t = (v - 50) / 50;                 // [-1, +1]
  const mag = Math.min(1, Math.abs(t));
  const hue = t >= 0 ? 8 : 212;            // топло ~червено / студено ~синьо
  const sat = 18 + mag * 62;               // 18% (до центъра) → 80%
  const light = 92 - mag * 44;             // 92% (бледо) → 48% (наситено)
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}
function renderHeatstrip() {
  const el = document.getElementById("heatstrip-panel");
  if (!el) return;
  const h = DATA.heatstrip;
  if (!h || !h.available) { el.style.display = "none"; return; }

  // Разредени етикети за месеците — само където сменя месецът.
  const monthAbbr = ["Яну","Фев","Мар","Апр","Май","Юни","Юли","Авг","Сеп","Окт","Ное","Дек"];
  let lastMonth = "";
  const monthCells = h.weeks.map(w => {
    const mo = w.slice(5, 7);
    if (mo !== lastMonth) { lastMonth = mo; return `<span class="hs-mo">${monthAbbr[parseInt(mo,10)-1]}</span>`; }
    return `<span class="hs-mo"></span>`;
  }).join("");

  const rows = h.categories.map(cat => {
    const cells = h.cells[cat].map((v, i) => {
      const val = v == null ? "—" : Math.round(v);
      const tip = `${cat} · седмица до ${h.weeks[i]} · momentum-перцентил ${val}`;
      return `<span class="hs-cell" style="background:${heatColor(v)}" title="${tip.replace(/"/g,"&quot;")}"></span>`;
    }).join("");
    return `<div class="hs-row">
      <span class="hs-label">${cat}</span>
      <div class="hs-cells">${cells}</div>
    </div>`;
  }).join("");

  el.innerHTML = `
    <div class="reg-head">
      <span class="reg-title">🔥 Ротация по сектори — ${h.n_weeks} седмици</span>
      <span class="reg-asof">медиен абсолютен momentum · студено → топло</span>
    </div>
    <div class="hs-grid">
      <div class="hs-row hs-monthrow"><span class="hs-label"></span><div class="hs-cells">${monthCells}</div></div>
      ${rows}
    </div>
    <div class="hs-legend">
      <span>студено</span>
      <span class="hs-bar"></span>
      <span>топло</span>
      <span class="hs-legend-note">клетка = медиен momentum-перцентил на сектора (0–100, 50 = средата на вселената)</span>
    </div>`;
  el.style.display = "block";
}

// ── Rotation Radar ─────────────────────────────────────────
function renderRadar() {
  const window = document.getElementById("window-filter").value;
  const quadCol = `quadrant_${window}`;
  const deltaCol = `delta_${window}`;
  const etfs = filteredByCategory("cat-filter");

  const quadrants = {
    "stable_winner": [],
    "riser": [],
    "decayer": [],
    "chronic_loser": []
  };

  etfs.forEach(e => {
    const q = e[quadCol];
    if (q && quadrants[q]) quadrants[q].push(e);
  });

  // Sort each quadrant
  quadrants.stable_winner.sort((a, b) => (b[deltaCol] || 0) - (a[deltaCol] || 0));
  quadrants.riser.sort((a, b) => (b[deltaCol] || 0) - (a[deltaCol] || 0));
  quadrants.decayer.sort((a, b) => (a[deltaCol] || 0) - (b[deltaCol] || 0));
  quadrants.chronic_loser.sort((a, b) => (a[deltaCol] || 0) - (b[deltaCol] || 0));

  Object.keys(quadrants).forEach(q => {
    const el = document.getElementById(`q-${q.replace("_", "-")}`);
    if (!el) return;
    el.innerHTML = quadrants[q].slice(0, 15).map(e => {
      const rank = e.current_rank != null ? e.current_rank.toFixed(0) : "—";
      const delta = e[deltaCol] != null ? e[deltaCol].toFixed(1) : null;
      const deltaHtml = delta != null
        ? `<span class="${parseFloat(delta) >= 0 ? 'positive' : 'negative'} q-delta">${parseFloat(delta) >= 0 ? "+" : ""}${delta}</span>`
        : "";
      const rs = e.is_bullish != null
        ? `<span style="font-size:0.7rem;color:${e.is_bullish ? 'var(--green)' : 'var(--red)'}">RS${e.is_bullish ? '▲' : '▼'}</span>`
        : "";
      return `<div class="q-item">
        <div class="q-item-left">
          <span class="q-ticker">${e.ticker}</span>
          <span class="q-cat-badge">${e.category || ""}</span>
          <span class="q-name">${e.name || ""}</span>
        </div>
        <div class="q-item-right">
          ${sparkline(e.spark)}
          ${rs}
          <span class="q-rank">${rank}%</span>
          ${deltaHtml}
        </div>
      </div>`;
    }).join("") || '<div style="color:var(--text-muted);font-size:0.85rem;padding:0.5rem">No ETFs in this quadrant</div>';
  });
}

// ── Screener ───────────────────────────────────────────────
function renderScreener() {
  const etfs = filteredByCategory("screener-cat-filter");
  const sorted = [...etfs].sort((a, b) => {
    const av = a[sortCol] != null ? parseFloat(a[sortCol]) : -Infinity;
    const bv = b[sortCol] != null ? parseFloat(b[sortCol]) : -Infinity;
    // sortDir = -1 -> низходящо (най-силните първи), +1 -> възходящо
    return sortDir * (av - bv);
  });

  lastScreenerSorted = sorted;
  const tbody = document.getElementById("screener-body");
  tbody.innerHTML = sorted.map(e => {
    const rankPct = e.percentile_rank != null ? parseFloat(e.percentile_rank) : null;
    const barWidth = rankPct != null ? Math.max(0, Math.min(100, rankPct)) : 0;
    const rankColor = rankPct >= 80 ? "var(--green)" : rankPct >= 50 ? "var(--accent)" : rankPct >= 20 ? "var(--yellow)" : "var(--red)";
    const rsIcon = e.is_bullish != null ? (e.is_bullish ? `<span style="color:var(--green)">▲</span>` : `<span style="color:var(--red)">▼</span>`) : "";

    return `<tr>
      <td class="ticker-cell">${e.ticker} ${rsIcon}</td>
      <td>${e.name || "—"}</td>
      <td class="cat-cell">${e.category || "—"}</td>
      <td class="num-cell bar-cell">
        <span class="rank-bar" style="width:${barWidth * 0.6}px;background:${rankColor}"></span>
        ${rankPct != null ? rankPct.toFixed(0) : "—"}
      </td>
      <td class="num-cell">${fmtPct(e.ret_1m)}</td>
      <td class="num-cell">${fmtPct(e.ret_3m)}</td>
      <td class="num-cell">${fmtPct(e.ret_12m)}</td>
      <td class="num-cell">${fmtNum(e.sharpe_12m)}</td>
      <td class="num-cell">${fmtPct(e.max_dd_12m)}</td>
      <td class="num-cell">${fmtPct(e.dist_52w_high)}</td>
      <td class="num-cell">${fmtPct(e.drawdown_now)}</td>
      <td class="num-cell">${e.atr_pct != null ? fmtNum(e.atr_pct, 1) + "%" : "—"}</td>
      <td class="num-cell">${e.stop_distance_pct != null ? fmtNum(e.stop_distance_pct, 1) + "%" : "—"}</td>
      <td class="num-cell">${e.expense_ratio != null ? fmtNum(e.expense_ratio, 2) + "%" : "—"}</td>
      <td class="num-cell">${e.yield != null ? fmtNum(e.yield, 2) + "%" : "—"}</td>
      <td class="num-cell">${e.pe_ratio != null ? fmtNum(e.pe_ratio, 1) : "—"}</td>
      <td class="num-cell">${fmtAUM(e.aum)}</td>
      <td class="num-cell">${fmtDollarVol(e.dollar_vol_20d, e.liquidity_flag)}</td>
      <td class="num-cell">${fmtFlow(e.est_flow_pct, e.est_flow, e.flow_dir, e.flow_window_days)}</td>
      <td class="num-cell">${e.beta_1y != null ? fmtNum(e.beta_1y, 2) : "—"}</td>
      <td class="num-cell">${e.corr_1y != null ? fmtNum(e.corr_1y, 2) : "—"}</td>
      <td class="num-cell" title="${concTooltip(e)}">${e.conc_top10 != null ? fmtNum(e.conc_top10, 1) + "%" : "—"}</td>
      <td class="num-cell" title="${cotTooltip(e)}">${e.cot_pctile != null ? e.cot_pctile + "%" : "—"}</td>
    </tr>`;
  }).join("");
}

// ── RS Lines ───────────────────────────────────────────────
function renderRS() {
  const catFilter = document.getElementById("rs-cat-filter").value;
  const sigFilter = document.getElementById("rs-signal-filter").value;

  let etfs = catFilter === "all" ? DATA.etfs : DATA.etfs.filter(e => e.category === catFilter);
  etfs = etfs.filter(e => e.is_bullish != null);

  if (sigFilter === "bullish") etfs = etfs.filter(e => e.is_bullish);
  if (sigFilter === "bearish") etfs = etfs.filter(e => !e.is_bullish);
  if (sigFilter === "crossover") etfs = etfs.filter(e => e.last_signal !== 0 && e.days_in_trend != null && e.days_in_trend <= 30);

  // Sort: bullish first, then by days_in_trend ascending
  etfs.sort((a, b) => {
    if (a.is_bullish !== b.is_bullish) return a.is_bullish ? -1 : 1;
    return (a.days_in_trend || 999) - (b.days_in_trend || 999);
  });

  const grid = document.getElementById("rs-grid");
  grid.innerHTML = etfs.map(e => {
    const bull = e.is_bullish;
    const days = e.days_in_trend != null ? Math.round(e.days_in_trend) + "d" : "—";
    const newCross = e.last_signal !== 0 && e.days_in_trend != null && e.days_in_trend <= 30;
    const newBadge = newCross ? `<span style="font-size:0.7rem;background:rgba(88,166,255,0.15);color:var(--accent);padding:0.1rem 0.3rem;border-radius:3px">NEW</span>` : "";
    return `<div class="rs-card ${bull ? 'bullish' : 'bearish'}">
      <div class="rs-card-header">
        <span class="rs-ticker">${e.ticker}</span>
        <span class="rs-signal ${bull ? 'bullish' : 'bearish'}">${bull ? 'BULLISH' : 'BEARISH'}</span>
      </div>
      <div class="rs-name">${e.name || "—"}</div>
      <div class="rs-bm">vs ${e.benchmark || "—"} ${newBadge}</div>
      <div class="rs-days">In trend: ${days}</div>
    </div>`;
  }).join("") || '<div style="color:var(--text-muted);padding:1rem">No ETFs match the current filter</div>';
}

// ── Regime Banner (ELANA Behavioral Barometer) ─────────────
function renderBarometer() {
  const el = document.getElementById("regime-banner");
  if (!el) return;
  const b = DATA.barometer;
  if (!b || !b.indicators) { el.style.display = "none"; return; }

  const conf = b.confluence || {};
  const zoneColor = z => z === "alarm" ? "var(--red)" : z === "base" ? "var(--green)"
    : z === "gray" ? "var(--yellow)" : "var(--text-muted)";
  const zoneBG = z => z === "alarm" ? "rgba(248,81,73,0.12)" : z === "base" ? "rgba(63,185,80,0.12)"
    : z === "gray" ? "rgba(210,153,34,0.12)" : "transparent";
  const zoneLabel = z => ({ base: "база", gray: "сива", alarm: "тревога", unknown: "—" }[z] || z);
  const arrow = t => t === "up" ? "↗" : t === "down" ? "↘" : "→";

  const aC = conf.alarm_count ?? 0, bC = conf.base_count ?? 0;
  let verdict, vcolor;
  if (conf.has_confluence && conf.direction === "alarm") {
    verdict = `⚠ Дислокация — ${aC} едновременни тревоги (${aC} тревога / ${bC} база)`; vcolor = "var(--red)";
  } else if (conf.has_confluence && conf.direction === "base") {
    verdict = `✓ Спокоен режим — превес на база (${bC} база / ${aC} тревога)`; vcolor = "var(--green)";
  } else {
    verdict = `Смесен сигнал (${aC} тревога / ${bC} база)`; vcolor = "var(--yellow)";
  }

  const thresholdLabel = i => i.kind === "robust_z"
    ? `z ${i.z != null ? i.z : "—"} (тревога |z|>${i.z_alarm})`
    : `база ${i.base_threshold} / тревога ${i.alarm_threshold}`;
  const chips = b.indicators.map(i => `
    <div class="reg-chip" style="border-color:${zoneColor(i.zone)};background:${zoneBG(i.zone)}">
      <span class="reg-name">${i.name}</span>
      <span class="reg-val" style="color:${zoneColor(i.zone)}">${i.value != null ? i.value : "—"} <span class="reg-arrow">${arrow(i.trend_4w)}</span></span>
      <span class="reg-zone">${zoneLabel(i.zone)} · ${thresholdLabel(i)}</span>
    </div>`).join("");

  el.innerHTML = `
    <div class="reg-head">
      <span class="reg-title">⬡ Барометър на дислокациите</span>
      <span class="reg-verdict" style="color:${vcolor}">${verdict}</span>
      <span class="reg-asof">${b.as_of || ""}</span>
    </div>
    <div class="reg-chips">${chips}</div>`;
  el.style.display = "block";
}

// ── Macro Context Strip (Tier 2 — keyless FRED overlays) ───
// Display-only режимен фон (НЕ е част от Барометър confluence).
function renderMacro() {
  const el = document.getElementById("macro-strip");
  if (!el) return;
  const m = DATA.macro;
  if (!m || !Array.isArray(m.items) || !m.items.length) { el.style.display = "none"; return; }
  const zColor = z => z === "alarm" ? "var(--red)" : z === "base" ? "var(--green)"
    : z === "gray" ? "var(--yellow)" : "var(--text-muted)";
  const zBG = z => z === "alarm" ? "rgba(248,81,73,0.12)" : z === "base" ? "rgba(63,185,80,0.12)"
    : z === "gray" ? "rgba(210,153,34,0.12)" : "transparent";
  const zLabel = z => ({ base: "норма", gray: "внимание", alarm: "стрес", unknown: "—" }[z] || z);
  const arrow = t => t === "up" ? "↗" : t === "down" ? "↘" : "→";
  const chips = m.items.map(i => `
    <div class="reg-chip" style="border-color:${zColor(i.zone)};background:${zBG(i.zone)}" title="${i.source}">
      <span class="reg-name">${i.name}</span>
      <span class="reg-val" style="color:${zColor(i.zone)}">${i.value != null ? i.value : "—"}`
        + `${i.z != null ? ` <span class="reg-zsub">z${i.z}</span>` : ""} `
        + `<span class="reg-arrow">${arrow(i.trend_4w)}</span></span>
      <span class="reg-zone">${zLabel(i.zone)} · ${i.note}</span>
    </div>`).join("");
  el.innerHTML = `
    <div class="reg-head">
      <span class="reg-title">🌐 Макро контекст</span>
      <span class="reg-asof">${m.as_of || ""}</span>
    </div>
    <div class="reg-chips">${chips}</div>`;
  el.style.display = "block";
}

// ── Macro Heatmap ──────────────────────────────────────────
function renderHeatmap() {
  const byCategory = {};
  DATA.etfs.forEach(e => {
    if (!e.category) return;
    if (!byCategory[e.category]) byCategory[e.category] = [];
    byCategory[e.category].push(e);
  });

  // Heatmap-ът е МАКРО изглед → ползва абсолютен momentum (abs_strength),
  // а не вътрешнокатегорийния percentile_rank (който по конструкция е ~50 за всяка
  // категория). Така малките категории не изскачат изкуствено.
  const strengthOf = e => (e.abs_strength != null ? e.abs_strength : e.current_rank);
  const catData = Object.entries(byCategory).map(([cat, etfs]) => {
    const ranks = etfs.map(strengthOf).filter(r => r != null);
    const median = ranks.length > 0
      ? ranks.sort((a, b) => a - b)[Math.floor(ranks.length / 2)]
      : null;
    const top3 = [...etfs]
      .filter(e => strengthOf(e) != null)
      .sort((a, b) => (strengthOf(b) || 0) - (strengthOf(a) || 0))
      .slice(0, 3);
    return { cat, median, etfs, top3 };
  }).sort((a, b) => (b.median || 0) - (a.median || 0));

  function scoreClass(v) {
    if (v == null) return "";
    if (v >= 75) return "score-very-high";
    if (v >= 60) return "score-high";
    if (v >= 40) return "score-mid";
    if (v >= 25) return "score-low";
    return "score-very-low";
  }

  const grid = document.getElementById("heatmap-grid");
  grid.innerHTML = catData.map(({ cat, median, etfs, top3 }) => {
    const sc = scoreClass(median);
    const barPct = median != null ? median.toFixed(0) : 0;
    const topHtml = top3.map(e => {
      const r = strengthOf(e);
      return `<span><span style="font-weight:700;color:var(--accent)">${e.ticker}</span> ${r != null ? r.toFixed(0) + "%" : ""}</span>`;
    }).join(" · ");
    return `<div class="heatmap-card ${sc}">
      <div class="heatmap-card-header">
        <span class="heatmap-cat">${cat}</span>
        <span class="heatmap-score">${median != null ? median.toFixed(0) : "—"}</span>
      </div>
      <div class="heatmap-bar-bg">
        <div class="heatmap-bar-fill" style="width:${barPct}%"></div>
      </div>
      <div class="heatmap-etfs">${etfs.length} ETFs tracked</div>
      <div class="heatmap-top">Leaders: ${topHtml || "—"}</div>
    </div>`;
  }).join("");
}

// ── Theme toggle (light / dark) ────────────────────────────
(function setupTheme() {
  const btn = document.getElementById("btn-theme");
  if (!btn) return;
  const isLight = () => document.documentElement.getAttribute("data-theme") === "light";
  const sync = () => { btn.textContent = isLight() ? "☀" : "☾"; };
  sync();
  btn.addEventListener("click", () => {
    const next = isLight() ? "dark" : "light";
    if (next === "light") document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("etf-theme", next); } catch (e) {}
    sync();
  });
})();

// ── Print / PDF snapshot (форсира светла тема, после възстановява) ──
(function setupPrint() {
  const btn = document.getElementById("btn-print");
  if (!btn) return;
  let restoreDark = false;
  btn.addEventListener("click", () => {
    restoreDark = document.documentElement.getAttribute("data-theme") !== "light";
    document.documentElement.setAttribute("data-theme", "light");
    window.print();
  });
  window.addEventListener("afterprint", () => {
    if (restoreDark) document.documentElement.removeAttribute("data-theme");
    restoreDark = false;
  });
})();

// ── Bootstrap ──────────────────────────────────────────────
loadData();
