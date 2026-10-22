/* XAUUSD AI Assist dashboard */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  // show times in the viewer's local timezone (the chart library works in UTC)
  const TZ_SHIFT = -new Date().getTimezoneOffset() * 60;
  const TF_SECONDS = { "15m": 900, "1h": 3600, "4h": 14400 };
  const toUnix = (iso) => Math.floor(new Date(iso).getTime() / 1000);
  const chartTime = (unix) => unix + TZ_SHIFT;
  const fmt = (n, d = 2) => (n == null || Number.isNaN(n) ? "—" : Number(n).toFixed(d));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const localTime = (iso) => new Date(iso).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });

  const state = { tf: "15m", analysis: null, priceLines: [], lastBarTime: null, trades: [], candles: [] };
  // the signal to draw on the chart (none when the AI analyst rejected it)
  const drawable = () => {
    const s = state.analysis && state.analysis.active_signal;
    return s && s.ai_status !== "rejected" ? s : null;
  };

  // ------------------------------------------------------------------ chart
  const el = $("#chart");
  const chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: { background: { color: css("--panel") }, textColor: css("--muted"), fontSize: 11 },
    grid: { vertLines: { color: "rgba(42,52,65,.5)" }, horzLines: { color: "rgba(42,52,65,.5)" } },
    rightPriceScale: { borderColor: css("--line") },
    timeScale: { borderColor: css("--line"), timeVisible: true, secondsVisible: false, rightOffset: 12 },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  const candles = chart.addCandlestickSeries({
    upColor: css("--buy"), downColor: css("--sell"), borderVisible: false,
    wickUpColor: css("--buy"), wickDownColor: css("--sell"),
    // keep the signal's SL and TP levels inside the visible price range
    autoscaleInfoProvider: (original) => {
      const res = original();
      const sig = drawable();
      if (!res || !sig) return res;
      const lv = [sig.sl, sig.tp1, sig.tp2, sig.tp3, sig.zone_low, sig.zone_high];
      res.priceRange.minValue = Math.min(res.priceRange.minValue, ...lv);
      res.priceRange.maxValue = Math.max(res.priceRange.maxValue, ...lv);
      return res;
    },
  });
  const emaSeries = {
    20: chart.addLineSeries({ color: css("--ema20"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    50: chart.addLineSeries({ color: css("--ema50"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    200: chart.addLineSeries({ color: css("--ema200"), lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
  };

  // overlay canvas for the entry zone box
  const overlay = $("#overlay");
  const ctx = overlay.getContext("2d");
  function drawOverlay() {
    const dpr = window.devicePixelRatio || 1;
    const w = el.clientWidth, h = el.clientHeight;
    if (overlay.width !== w * dpr || overlay.height !== h * dpr) {
      overlay.width = w * dpr; overlay.height = h * dpr;
      overlay.style.width = w + "px"; overlay.style.height = h + "px";
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const sig = drawable();
    if (!sig || !state.candles.length) return requestAnimationFrame(drawOverlay);
    const plotRight = w - chart.priceScale("right").width();
    const y1 = candles.priceToCoordinate(sig.zone_high);
    const y2 = candles.priceToCoordinate(sig.zone_low);
    const tfSec = TF_SECONDS[state.tf];
    const start = chartTime(Math.floor(toUnix(sig.created) / tfSec) * tfSec);
    let x1 = chart.timeScale().timeToCoordinate(start);
    const lastT = state.candles[state.candles.length - 1].time;
    let x2 = chart.timeScale().timeToCoordinate(Math.min(chartTime(toUnix(sig.valid_until)), lastT));
    if (x1 == null) x1 = 0;
    if (x2 == null || x2 < x1) x2 = plotRight;
    x2 = Math.max(x2, plotRight - 4);  // extend the zone to the right edge
    if (y1 != null && y2 != null) {
      const buy = sig.direction === "BUY";
      ctx.fillStyle = buy ? "rgba(34,197,94,.16)" : "rgba(239,68,68,.16)";
      ctx.strokeStyle = buy ? "rgba(34,197,94,.8)" : "rgba(239,68,68,.8)";
      ctx.lineWidth = 1;
      const top = Math.min(y1, y2), height = Math.max(Math.abs(y2 - y1), 2);
      ctx.fillRect(x1, top, Math.min(x2, plotRight) - x1, height);
      ctx.strokeRect(x1 + 0.5, top + 0.5, Math.min(x2, plotRight) - x1 - 1, height - 1);
      ctx.fillStyle = buy ? css("--buy") : css("--sell");
      ctx.font = "600 11px system-ui, sans-serif";
      const label = `${sig.direction} ZONE ${fmt(sig.zone_low)}–${fmt(sig.zone_high)}`;
      // leave ~70px free at the right edge for the price-line tags (Entry, TP1, SL ...)
      const lx = Math.max(4, Math.min(x1 + 6, plotRight - ctx.measureText(label).width - 70));
      ctx.fillText(label, lx, top - 5);
    }
    requestAnimationFrame(drawOverlay);
  }
  requestAnimationFrame(drawOverlay);

  function setPriceLines(sig, levels) {
    state.priceLines.forEach((l) => candles.removePriceLine(l));
    state.priceLines = [];
    const add = (price, color, title, style = LightweightCharts.LineStyle.Solid, width = 1) => {
      if (price == null) return;
      state.priceLines.push(candles.createPriceLine({ price, color, title, lineStyle: style, lineWidth: width, axisLabelVisible: true }));
    };
    if (sig) {
      add(sig.sl, css("--sell"), "SL", LightweightCharts.LineStyle.Dashed, 2);
      add(sig.tp1, css("--buy"), "TP1");
      add(sig.tp2, css("--buy"), "TP2");
      add(sig.tp3, css("--buy"), "TP3", LightweightCharts.LineStyle.Solid, 2);
      add(sig.entry, css("--gold"), "Entry", LightweightCharts.LineStyle.Dotted);
    }
    if (levels) {
      const faint = "rgba(139,152,168,.55)";
      add(levels.prev_day_high, faint, "PDH", LightweightCharts.LineStyle.SparseDotted);
      add(levels.prev_day_low, faint, "PDL", LightweightCharts.LineStyle.SparseDotted);
    }
  }

  function setMarkers() {
    const tfSec = TF_SECONDS[state.tf];
    const first = state.candles.length ? state.candles[0].time : 0;
    const markers = state.trades
      .filter((t) => t.fill_time)
      .map((t) => {
        const tt = chartTime(Math.floor(toUnix(t.signal_time) / tfSec) * tfSec);
        const buy = t.direction === "BUY";
        const win = t.result_r > 0;
        return {
          time: tt,
          position: buy ? "belowBar" : "aboveBar",
          color: win ? css("--buy") : css("--sell"),
          shape: buy ? "arrowUp" : "arrowDown",
          text: `${t.grade} ${t.result_r > 0 ? "+" : ""}${fmt(t.result_r, 1)}R`,
        };
      })
      .filter((m) => m.time >= first)
      .sort((a, b) => a.time - b.time);
    candles.setMarkers(markers);
  }

  // ------------------------------------------------------------------ data
  async function api(path) {
    const r = await fetch(path);
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch (_) { /* not json */ }
      throw new Error(msg);
    }
    return r.json();
  }

  function showError(msg) {
    const box = $("#chart-error");
    box.hidden = !msg;
    box.textContent = msg ? `Cannot load data: ${msg}` : "";
  }

  async function loadCandles(fit = false) {
    try {
      const d = await api(`/api/candles?tf=${state.tf}&limit=${state.tf === "15m" ? 1500 : 800}`);
      state.candles = d.candles.map((c) => ({ ...c, time: chartTime(c.time) }));
      candles.setData(state.candles);
      for (const n of [20, 50, 200]) emaSeries[n].setData(d.ema[n].map((p) => ({ ...p, time: chartTime(p.time) })));
      const last = state.candles[state.candles.length - 1];
      $("#price").textContent = fmt(last.close);
      setMarkers();
      if (fit) chart.timeScale().setVisibleLogicalRange({ from: state.candles.length - 160, to: state.candles.length + 12 });
      showError(null);
    } catch (e) {
      showError(e.message);
    }
  }

  async function loadAnalysis() {
    try {
      const a = await api("/api/analysis");
      state.analysis = a;
      renderSignal(a);
      renderWhy(a);
      renderContext(a);
      renderVotes(a);
      renderCalendar(a.upcoming_events || []);
      setPriceLines(drawable(), a.levels);
      const reg = $("#regime");
      reg.textContent = { trend_up: "Trending up", trend_down: "Trending down", range: "Ranging", volatile: "Very volatile" }[a.regime] || a.regime;
      reg.className = `badge ${a.regime}`;
      const age = a.data_age_minutes;
      const ageText = age < 90 ? `${Math.round(age)} min` : age < 2880 ? `${Math.round(age / 60)} h` : `${Math.round(age / 1440)} days`;
      $("#updated").textContent = `Last candle ${localTime(a.time)} · ${ageText} ago${age > 60 ? " (market closed or data delayed)" : ""}`;
    } catch (e) {
      $("#signal").innerHTML = `<div class="muted">Analysis unavailable: ${esc(e.message)}</div>`;
    }
  }

  async function loadNews() {
    try { renderNews(await api("/api/news")); } catch (e) { $("#tab-news").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  }

  // ------------------------------------------------------------------ render
  const AI_LABEL = {
    confirmed: ["yes", "AI confirmed this trade"],
    adjusted: ["yes", "AI confirmed and adjusted the levels"],
    rejected: ["no", "AI rejected this trade"],
    analysing: ["wait", "AI is analysing…"],
    error: ["no", "AI analyst unavailable — strategies only"],
    "not reviewed": ["idle", "Not reviewed by AI"],
    "ai signal": ["yes", "Trade found by the AI analyst"],
  };

  function aiBlock(s) {
    if (!s.ai_status) return "";
    const [cls, label] = AI_LABEL[s.ai_status] || ["idle", s.ai_status];
    const v = s.ai || {};
    let body = "";
    if (v.status === "ok") {
      const list = (items, c) => (items || []).map((t) => `<li class="${c}">${esc(t)}</li>`).join("");
      body = `<p>${esc(v.summary)}</p><ul class="why">${list(v.reasons, "yes")}${list(v.risks, "no")}</ul>
        ${v.problems && v.problems.length ? `<p class="muted">Levels kept from strategies: ${esc(v.problems.join("; "))}</p>` : ""}
        <div class="muted small">${esc([v.provider, v.model].filter(Boolean).join(" · "))}</div>`;
    } else if (v.status === "error") {
      body = `<p class="muted small">${esc(v.error)}</p>`;
    }
    const conf = v.status === "ok" ? `<span class="ai-conf">${v.confidence}%</span>` : "";
    return `<div class="ai-box ${cls}"><div class="ai-head"><b>${label}</b>${conf}</div>${body}</div>`;
  }

  function renderSignal(a) {
    const s = a.active_signal;
    const box = $("#signal");
    if (!s) {
      box.className = "card signal-card";
      const items = (a.blocked || []).map((b) => `<li>${esc(b)}</li>`).join("");
      const scan = a.ai_scan;
      let scanText = "";
      if (scan && (scan.status === "pending" || scan.status === "queued")) scanText = '<div class="ai-box wait"><b>AI is scanning the market…</b></div>';
      else if (scan && scan.status === "ok") scanText = `<div class="ai-box idle"><b>AI: ${scan.action === "NO_TRADE" ? "no trade right now" : esc(scan.action)}</b><p>${esc(scan.summary)}</p></div>`;
      box.innerHTML = `
        <div class="sig-head"><span class="sig-dir">No trade</span><span class="grade">—</span></div>
        <p class="muted">Waiting for a good setup. Current reasons:</p>
        <ul class="blocked">${items || "<li>No setup on the latest candle</li>"}</ul>${scanText}`;
      return;
    }
    const dir = s.direction.toLowerCase();
    const rejected = s.ai_status === "rejected";
    box.className = `card signal-card ${rejected ? "rejected" : dir}`;
    const heading = rejected ? "Rejected signal — no trade" : s.open ? "Active signal" : "Last signal (finished) — waiting for a new setup";
    const who = s.source === "ai" ? "found by the AI analyst" : `${s.strategies.length} strategies agree`;
    const ml = s.ml_probability != null ? ` · ML: ${fmt(s.ml_probability, 0)}% chance of TP1` : "";
    box.innerHTML = `
      <div class="muted">${heading} · ${localTime(s.created)}</div>
      <div class="sig-head">
        <span class="sig-dir ${rejected ? "" : dir}">${rejected ? "<s>" + s.direction + "</s>" : s.direction}</span>
        <span class="grade g-${s.grade.replace("+", "p")}" title="Signal grade">${s.grade}</span>
      </div>
      <div class="muted">Score ${fmt(s.score, 0)}/100 · ${who}${ml}</div>
      <div class="scorebar"><i style="width:${Math.min(100, s.score)}%"></i></div>
      ${aiBlock(s)}
      <dl class="kv${rejected ? " dim" : ""}">
        <dt>Entry zone</dt><dd class="zone">${fmt(s.zone_low)} – ${fmt(s.zone_high)}</dd>
        <dt>Entry (limit)</dt><dd>${fmt(s.entry)}</dd>
        <dt>Stop loss</dt><dd class="sl">${fmt(s.sl)}</dd>
        <dt>TP1 · close 50%</dt><dd class="tp">${fmt(s.tp1)}</dd>
        <dt>TP2 · close 30%</dt><dd class="tp">${fmt(s.tp2)}</dd>
        <dt>TP3 · runner</dt><dd class="tp">${fmt(s.tp3)}</dd>
        <dt>Risk : reward (TP2)</dt><dd>1 : ${fmt(s.rr_tp2, 1)}</dd>
        <dt>Lot size</dt><dd>${fmt(s.lot)} lot (≈ $${fmt(s.risk_usd, 0)} risk)</dd>
        <dt>Valid until</dt><dd>${localTime(s.valid_until)}</dd>
      </dl>
      ${s.engine_levels ? `<div class="muted small">Strategy levels before AI: SL ${fmt(s.engine_levels.sl)} · TP1 ${fmt(s.engine_levels.tp1)} · zone ${fmt(s.engine_levels.zone_low)}–${fmt(s.engine_levels.zone_high)}</div>` : ""}
      <div class="status">Status: <b>${esc(s.status)}</b></div>`;
  }

  function renderWhy(a) {
    const s = a.active_signal;
    const li = [];
    if (s) {
      s.reasons.forEach((r) => li.push(`<li class="yes">${esc(r)}</li>`));
      s.against.forEach((r) => li.push(`<li class="no">${esc(r)}</li>`));
    } else {
      (a.votes || []).forEach((v) => li.push(`<li class="note">${esc(v.direction)}: ${esc(v.reason)}</li>`));
    }
    (a.notes || []).forEach((n) => li.push(`<li class="note">${esc(n)}</li>`));
    $("#why").innerHTML = li.join("") || `<li class="muted">No active strategy votes right now.</li>`;
  }

  function biasText(b) {
    if (b == null) return "—";
    const cls = b > 0.15 ? "pos" : b < -0.15 ? "neg" : "muted";
    const word = b > 0.15 ? "bullish" : b < -0.15 ? "bearish" : "neutral";
    return `<span class="${cls}">${word} (${b > 0 ? "+" : ""}${fmt(b, 2)})</span>`;
  }

  function renderContext(a) {
    const im = a.intermarket || {};
    const L = a.levels || {};
    const rows = [
      ["News bias for gold", biasText(a.news_bias)],
      ["Dollar & yields bias", im.ok ? biasText(im.bias) : '<span class="muted">unavailable</span>'],
      ["US Dollar Index (24h)", im.dxy != null ? `${fmt(im.dxy)} (${im.dxy_change_pct > 0 ? "+" : ""}${fmt(im.dxy_change_pct)}%)` : "—"],
      ["US 10Y yield (24h)", im.us10y != null ? `${fmt(im.us10y, 3)}% (${im.us10y_change > 0 ? "+" : ""}${fmt(im.us10y_change, 3)})` : "—"],
      ["Buy / sell strength", `<span class="pos">${fmt(a.buy_strength)}</span> / <span class="neg">${fmt(a.sell_strength)}</span>`],
      ["Previous day high / low", `${fmt(L.prev_day_high)} / ${fmt(L.prev_day_low)}`],
      ["Asian range", `${fmt(L.asia_low)} – ${fmt(L.asia_high)}`],
      ["ATR (15m)", fmt(a.atr)],
    ];
    $("#context").innerHTML = rows.map(([k, v]) => `<div class="row"><span class="muted">${k}</span><span>${v}</span></div>`).join("");
  }

  let strategyList = [];
  function renderVotes(a) {
    const active = Object.fromEntries((a.votes || []).map((v) => [v.strategy, v]));
    const rows = strategyList.map((s) => {
      const v = active[s.name];
      const pill = v ? `<span class="pill ${v.direction}">${v.direction}</span>` : `<span class="pill idle">idle</span>`;
      return `<tr><td>${pill}</td><td><b>${esc(s.label)}</b><div class="muted">${esc(v ? v.reason : s.description)}</div></td>
        <td>${v ? fmt(v.confidence * 100, 0) + "%" : ""}</td><td>${v ? fmt(v.zone_low) + " – " + fmt(v.zone_high) : ""}</td></tr>`;
    }).join("");
    $("#tab-votes").innerHTML = `<div class="table-scroll"><table><thead><tr><th>Vote</th><th>Strategy</th><th>Confidence</th><th>Zone</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function renderNews(n) {
    const rows = (n.headlines || []).slice(0, 40).map((h) => `
      <tr><td><span class="pill ${h.impact}">${h.impact}</span></td>
      <td><a href="${/^https?:\/\//i.test(h.link || "") ? esc(h.link) : "#"}" target="_blank" rel="noopener noreferrer">${esc(h.title)}</a>
      <div class="muted">${esc(h.source)} · ${localTime(h.time)} · ${esc(h.reason)}</div></td></tr>`).join("");
    $("#tab-news").innerHTML = `<p class="muted">News bias: ${biasText(n.bias)} · analysed by ${esc(n.model)}</p>
      <div class="table-scroll"><table><tbody>${rows || '<tr><td class="muted">No headlines loaded (check internet connection).</td></tr>'}</tbody></table></div>`;
  }

  function renderCalendar(events) {
    const rows = events.map((e) => `<tr><td>${localTime(e.time)}</td><td><span class="pill ${e.impact}">${e.impact}</span></td>
      <td>${esc(e.title)}</td><td class="muted">F: ${esc(e.forecast) || "—"} · P: ${esc(e.previous) || "—"}</td></tr>`).join("");
    $("#tab-calendar").innerHTML = `<p class="muted">USD events. New signals are blocked 30 minutes before and after High-impact news.</p>
      <div class="table-scroll"><table><thead><tr><th>Time</th><th>Impact</th><th>Event</th><th>Forecast / Previous</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="muted">No upcoming events loaded.</td></tr>'}</tbody></table></div>`;
  }

  function statRow(name, s) {
    if (!s || !s.trades) return `<tr><td>${esc(name)}</td><td>${s ? s.signals : 0}</td><td colspan="6" class="muted">no filled trades</td></tr>`;
    const cls = s.total_r >= 0 ? "pos" : "neg";
    return `<tr><td>${esc(name)}</td><td>${s.signals}</td><td>${s.trades}</td><td>${fmt(s.win_rate_tp1, 1)}%</td>
      <td>${fmt(s.full_losses_pct, 1)}%</td><td class="${cls}">${fmt(s.avg_r, 2)}R</td><td class="${cls}">${fmt(s.total_r, 1)}R</td>
      <td>${s.profit_factor ?? "—"}</td></tr>`;
  }

  async function runBacktest() {
    const out = $("#bt");
    out.innerHTML = '<p class="muted">Running…</p>';
    try {
      const r = await api("/api/backtest");
      state.trades = r.trades;
      setMarkers();
      const s = r.stats;
      const head = "<tr><th></th><th>Signals</th><th>Trades</th><th>Win rate (TP1)</th><th>Full losses</th><th>Avg</th><th>Total</th><th>Profit factor</th></tr>";
      const grades = ["all", "A+", "A", "B"].map((g) => statRow(g === "all" ? "All signals" : `Grade ${g}`, s[g])).join("");
      const strat = Object.entries(s.by_strategy).map(([k, v]) => statRow(k, v)).join("");
      const m = state.ml;
      const mlHtml = m ? `<h3 style="margin-top:14px">ML model — test on unseen data (${new Date(m.test_period_from).toLocaleDateString()} → ${new Date(m.data_to).toLocaleDateString()})</h3>
        <div class="table-scroll"><table><thead>${head}</thead><tbody>
        ${statRow("All candidates", { signals: m.test_all_candidates.trades, ...m.test_all_candidates, full_losses_pct: null })}
        ${statRow("Approved by model", { signals: m.test_model_approved.trades, ...m.test_model_approved, full_losses_pct: null })}
        </tbody></table></div><p class="muted">AUC ${m.test_auc ?? "—"} (0.5 = no skill) · threshold ${fmt(m.threshold * 100, 0)}% · trained on ${m.candidates} candidate trades.</p>` :
        `<p class="muted">No ML model trained yet. Run <code>python -m backend.app.ml --csv your_history.csv</code>.</p>`;
      out.innerHTML = `
        <p class="muted">${new Date(r.start).toLocaleDateString()} → ${new Date(r.end).toLocaleDateString()} · ${r.bars} candles · max drawdown ${fmt(s.all.max_drawdown_r, 1)}R.
        Arrows on the chart show each trade. Results include spread; news filters are not applied in backtests.</p>
        <div class="table-scroll"><table><thead>${head}</thead><tbody>${grades}</tbody></table></div>
        ${mlHtml}
        <h3 style="margin-top:14px">By strategy (trades where it agreed)</h3>
        <div class="table-scroll"><table><thead>${head}</thead><tbody>${strat}</tbody></table></div>`;
    } catch (e) {
      out.innerHTML = `<p class="muted">Backtest failed: ${esc(e.message)}</p>`;
    }
  }

  // ------------------------------------------------------------------ UI events
  document.querySelectorAll(".tf button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tf button").forEach((x) => x.classList.toggle("active", x === b));
    state.tf = b.dataset.tf;
    loadCandles(true);
  }));
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${b.dataset.tab}`));
  }));
  $("#run-bt").addEventListener("click", runBacktest);

  // ------------------------------------------------------------------ start
  (async () => {
    try {
      const st = await api("/api/status");
      strategyList = st.strategies;
      state.ml = st.ml_model;
      const mlText = st.ml_model ? `ML filter on (test win rate ${st.ml_model.test_model_approved.win_rate_tp1 ?? "—"}%)` : "ML filter off";
      const aiText = st.ai_provider ? `AI: ${st.ai_provider} (${st.ai_signal_mode})` : "AI: off (no API key)";
      $("#source").textContent = `Data: ${st.provider} · ${aiText} · ${mlText}`;
    } catch (_) { /* shown elsewhere */ }
    await loadCandles(true);
    await loadAnalysis();
    loadNews();
    setInterval(() => { loadCandles(false); loadAnalysis(); }, 30000);
    setInterval(loadNews, 300000);
  })();
})();
