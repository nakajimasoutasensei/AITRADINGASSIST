/* XAUUSD AI Assist dashboard */
(() => {
  "use strict";

  const { t, tr } = window.I18N;
  const $ = (s) => document.querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  // show times in the viewer's local timezone (the chart library works in UTC)
  const TZ_SHIFT = -new Date().getTimezoneOffset() * 60;
  const TF_SECONDS = { "15m": 900, "1h": 3600, "4h": 14400 };
  const toUnix = (iso) => Math.floor(new Date(iso).getTime() / 1000);
  const chartTime = (unix) => unix + TZ_SHIFT;
  const fmt = (n, d = 2) => (n == null || Number.isNaN(n) ? "—" : Number(n).toFixed(d));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const localTime = (iso) => new Date(iso).toLocaleString(I18N.locale, { weekday: "short", hour: "2-digit", minute: "2-digit" });
  const localDate = (iso) => new Date(iso).toLocaleDateString(I18N.locale);

  // latest data from the server, kept so the page can be redrawn when the language changes
  const state = { tf: "15m", analysis: null, news: null, status: null, backtest: null, priceLines: [], trades: [], candles: [] };
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
      const label = t("zone_label", { dir: sig.direction, lo: fmt(sig.zone_low), hi: fmt(sig.zone_high) });
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
      .filter((tr_) => tr_.fill_time)
      .map((tr_) => {
        const tt = chartTime(Math.floor(toUnix(tr_.signal_time) / tfSec) * tfSec);
        const buy = tr_.direction === "BUY";
        const win = tr_.result_r > 0;
        return {
          time: tt,
          position: buy ? "belowBar" : "aboveBar",
          color: win ? css("--buy") : css("--sell"),
          shape: buy ? "arrowUp" : "arrowDown",
          text: `${tr_.grade} ${tr_.result_r > 0 ? "+" : ""}${fmt(tr_.result_r, 1)}R`,
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
    box.textContent = msg ? t("cannot_load", { msg }) : "";
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
      state.analysis = await api("/api/analysis");
      state.analysisError = null;
      setPriceLines(drawable(), state.analysis.levels);
    } catch (e) {
      state.analysisError = e.message;
    }
    renderAnalysis();
  }

  async function loadNews() {
    try { state.news = await api("/api/news"); state.newsError = null; } catch (e) { state.newsError = e.message; }
    renderNews();
  }

  async function loadStatus() {
    try { state.status = await api("/api/status"); } catch (_) { /* shown elsewhere */ }
    renderStatus();
  }

  // ------------------------------------------------------------------ render
  const AI_LABEL = {
    confirmed: ["yes", "ai_confirmed"],
    adjusted: ["yes", "ai_adjusted"],
    rejected: ["no", "ai_rejected"],
    analysing: ["wait", "ai_analysing"],
    error: ["no", "ai_error"],
    "not reviewed": ["idle", "ai_not_reviewed"],
    "ai signal": ["yes", "ai_signal"],
  };

  function aiBlock(s) {
    if (!s.ai_status) return "";
    const [cls, key] = AI_LABEL[s.ai_status] || ["idle", s.ai_status];
    const v = s.ai || {};
    let body = "";
    if (v.status === "ok") {
      const list = (items, c) => (items || []).map((x) => `<li class="${c}">${esc(x)}</li>`).join("");
      const problems = (v.problems || []).map(tr).join("; ");
      body = `<p>${esc(I18N.aiText(v, "summary"))}</p>
        <ul class="why">${list(I18N.aiText(v, "reasons"), "yes")}${list(I18N.aiText(v, "risks"), "no")}</ul>
        ${problems ? `<p class="muted">${esc(t("levels_kept", { p: problems }))}</p>` : ""}
        <div class="muted small">${esc([v.provider, v.model].filter(Boolean).join(" · "))}</div>`;
    } else if (v.status === "error") {
      body = `<p class="muted small">${esc(v.error)}</p>`;
    }
    const conf = v.status === "ok" ? `<span class="ai-conf">${v.confidence}%</span>` : "";
    return `<div class="ai-box ${cls}"><div class="ai-head"><b>${esc(t(key))}</b>${conf}</div>${body}</div>`;
  }

  function renderSignal(a) {
    const s = a.active_signal;
    const box = $("#signal");
    if (!s) {
      box.className = "card signal-card";
      const items = (a.blocked || []).map((b) => `<li>${esc(tr(b))}</li>`).join("");
      const scan = a.ai_scan;
      let scanText = "";
      if (scan && (scan.status === "pending" || scan.status === "queued")) {
        scanText = `<div class="ai-box wait"><b>${esc(t("ai_scanning"))}</b></div>`;
      } else if (scan && scan.status === "ok") {
        const action = scan.action === "NO_TRADE" ? t("ai_no_trade_now") : scan.action;
        scanText = `<div class="ai-box idle"><b>AI: ${esc(action)}</b><p>${esc(I18N.aiText(scan, "summary"))}</p></div>`;
      }
      box.innerHTML = `
        <div class="sig-head"><span class="sig-dir">${esc(t("no_trade"))}</span><span class="grade">—</span></div>
        <p class="muted">${esc(t("waiting_setup"))}</p>
        <ul class="blocked">${items || `<li>${esc(t("no_setup"))}</li>`}</ul>${scanText}`;
      return;
    }
    const dir = s.direction.toLowerCase();
    const rejected = s.ai_status === "rejected";
    box.className = `card signal-card ${rejected ? "rejected" : dir}`;
    const heading = t(rejected ? "heading_rejected" : s.open ? "heading_active" : "heading_finished");
    const who = s.source === "ai" ? t("who_ai") : t("who_n", { n: s.strategies.length });
    const ml = s.ml_probability != null ? t("ml_prob", { p: fmt(s.ml_probability, 0) }) : "";
    box.innerHTML = `
      <div class="muted">${esc(heading)} · ${localTime(s.created)}</div>
      <div class="sig-head">
        <span class="sig-dir ${rejected ? "" : dir}">${rejected ? "<s>" + s.direction + "</s>" : s.direction}</span>
        <span class="grade g-${s.grade.replace("+", "p")}" title="${esc(t("grade_title"))}">${s.grade}</span>
      </div>
      <div class="muted">${esc(t("score", { s: fmt(s.score, 0) }))} · ${esc(who)}${esc(ml)}</div>
      <div class="scorebar"><i style="width:${Math.min(100, s.score)}%"></i></div>
      ${aiBlock(s)}
      <dl class="kv${rejected ? " dim" : ""}">
        <dt>${t("kv_zone")}</dt><dd class="zone">${fmt(s.zone_low)} – ${fmt(s.zone_high)}</dd>
        <dt>${t("kv_entry")}</dt><dd>${fmt(s.entry)}</dd>
        <dt>${t("kv_sl")}</dt><dd class="sl">${fmt(s.sl)}</dd>
        <dt>${t("kv_tp1")}</dt><dd class="tp">${fmt(s.tp1)}</dd>
        <dt>${t("kv_tp2")}</dt><dd class="tp">${fmt(s.tp2)}</dd>
        <dt>${t("kv_tp3")}</dt><dd class="tp">${fmt(s.tp3)}</dd>
        <dt>${t("kv_rr")}</dt><dd>1 : ${fmt(s.rr_tp2, 1)}</dd>
        <dt>${t("kv_lot")}</dt><dd>${esc(t("kv_lot_val", { lot: fmt(s.lot), usd: fmt(s.risk_usd, 0) }))}</dd>
        <dt>${t("kv_valid")}</dt><dd>${localTime(s.valid_until)}</dd>
      </dl>
      ${s.engine_levels ? `<div class="muted small">${esc(t("engine_levels", { sl: fmt(s.engine_levels.sl), tp1: fmt(s.engine_levels.tp1), z: `${fmt(s.engine_levels.zone_low)}–${fmt(s.engine_levels.zone_high)}` }))}</div>` : ""}
      <div class="status">${t("status")}: <b>${esc(tr(s.status))}</b></div>`;
  }

  function renderWhy(a) {
    const s = a.active_signal;
    const li = [];
    if (s) {
      s.reasons.forEach((r) => li.push(`<li class="yes">${esc(tr(r))}</li>`));
      s.against.forEach((r) => li.push(`<li class="no">${esc(tr(r))}</li>`));
    } else {
      (a.votes || []).forEach((v) => li.push(`<li class="note">${esc(v.direction)}: ${esc(tr(v.reason))}</li>`));
    }
    (a.notes || []).forEach((n) => li.push(`<li class="note">${esc(tr(n))}</li>`));
    $("#why").innerHTML = li.join("") || `<li class="muted">${esc(t("no_votes"))}</li>`;
  }

  function biasText(b) {
    if (b == null) return "—";
    const cls = b > 0.15 ? "pos" : b < -0.15 ? "neg" : "muted";
    const word = t(b > 0.15 ? "bullish" : b < -0.15 ? "bearish" : "neutral");
    return `<span class="${cls}">${word} (${b > 0 ? "+" : ""}${fmt(b, 2)})</span>`;
  }

  function renderContext(a) {
    const im = a.intermarket || {};
    const L = a.levels || {};
    const rows = [
      ["ctx_news", biasText(a.news_bias)],
      ["ctx_dollar", im.ok ? biasText(im.bias) : `<span class="muted">${t("unavailable")}</span>`],
      ["ctx_dxy", im.dxy != null ? `${fmt(im.dxy)} (${im.dxy_change_pct > 0 ? "+" : ""}${fmt(im.dxy_change_pct)}%)` : "—"],
      ["ctx_us10y", im.us10y != null ? `${fmt(im.us10y, 3)}% (${im.us10y_change > 0 ? "+" : ""}${fmt(im.us10y_change, 3)})` : "—"],
      ["ctx_strength", `<span class="pos">${fmt(a.buy_strength)}</span> / <span class="neg">${fmt(a.sell_strength)}</span>`],
      ["ctx_pd", `${fmt(L.prev_day_high)} / ${fmt(L.prev_day_low)}`],
      ["ctx_asia", `${fmt(L.asia_low)} – ${fmt(L.asia_high)}`],
      ["ctx_atr", fmt(a.atr)],
    ];
    $("#context").innerHTML = rows.map(([k, v]) => `<div class="row"><span class="muted">${t(k)}</span><span>${v}</span></div>`).join("");
  }

  function renderVotes(a) {
    const active = Object.fromEntries((a.votes || []).map((v) => [v.strategy, v]));
    const list = (state.status && state.status.strategies) || [];
    const rows = list.map((st) => {
      const v = active[st.name];
      const { label, description } = I18N.strategy(st.name, st.label, st.description);
      const pill = v ? `<span class="pill ${v.direction}">${v.direction}</span>` : `<span class="pill idle">${t("idle")}</span>`;
      return `<tr><td>${pill}</td><td><b>${esc(label)}</b><div class="muted">${esc(v ? tr(v.reason) : description)}</div></td>
        <td>${v ? fmt(v.confidence * 100, 0) + "%" : ""}</td><td>${v ? fmt(v.zone_low) + " – " + fmt(v.zone_high) : ""}</td></tr>`;
    }).join("");
    $("#tab-votes").innerHTML = `<div class="table-scroll"><table><thead><tr><th>${t("th_vote")}</th><th>${t("th_strategy")}</th>
      <th>${t("th_confidence")}</th><th>${t("th_zone")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function renderAnalysis() {
    if (state.analysisError && !state.analysis) {
      $("#signal").innerHTML = `<div class="muted">${esc(t("analysis_unavailable", { msg: state.analysisError }))}</div>`;
      return;
    }
    const a = state.analysis;
    if (!a) return;
    renderSignal(a);
    renderWhy(a);
    renderContext(a);
    renderVotes(a);
    renderCalendar(a.upcoming_events || []);
    const reg = $("#regime");
    reg.textContent = t(`regime_${a.regime}`);
    reg.className = `badge ${a.regime}`;
    const age = a.data_age_minutes;
    const ageText = age < 90 ? t("age_min", { n: Math.round(age) }) : age < 2880 ? t("age_h", { n: Math.round(age / 60) }) : t("age_days", { n: Math.round(age / 1440) });
    $("#updated").textContent = t("updated", { time: localTime(a.time), age: ageText }) + (age > 60 ? t("market_closed") : "");
  }

  function renderNews() {
    if (state.newsError && !state.news) {
      $("#tab-news").innerHTML = `<p class="muted">${esc(state.newsError)}</p>`;
      return;
    }
    const n = state.news;
    if (!n) return;
    const rows = (n.headlines || []).slice(0, 40).map((h) => `
      <tr><td><span class="pill ${h.impact}">${t(h.impact)}</span></td>
      <td><a href="${/^https?:\/\//i.test(h.link || "") ? esc(h.link) : "#"}" target="_blank" rel="noopener noreferrer">${esc(h.title)}</a>
      <div class="muted">${esc(h.source)} · ${localTime(h.time)} · ${esc(tr(I18N.lang === "id" && h.reason_id ? h.reason_id : h.reason))}</div></td></tr>`).join("");
    $("#tab-news").innerHTML = `<p class="muted">${t("news_bias", { b: biasText(n.bias), m: esc(n.model) })}</p>
      <div class="table-scroll"><table><tbody>${rows || `<tr><td class="muted">${t("no_headlines")}</td></tr>`}</tbody></table></div>`;
  }

  function renderCalendar(events) {
    const rows = events.map((e) => `<tr><td>${localTime(e.time)}</td><td><span class="pill ${e.impact}">${t(`impact_${e.impact}`)}</span></td>
      <td>${esc(e.title)}</td><td class="muted">${esc(t("cal_fp", { f: e.forecast || "—", p: e.previous || "—" }))}</td></tr>`).join("");
    $("#tab-calendar").innerHTML = `<p class="muted">${t("cal_intro")}</p>
      <div class="table-scroll"><table><thead><tr><th>${t("th_time")}</th><th>${t("th_impact")}</th><th>${t("th_event")}</th><th>${t("th_fp")}</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="4" class="muted">${t("no_events")}</td></tr>`}</tbody></table></div>`;
  }

  function statRow(name, s) {
    if (!s || !s.trades) return `<tr><td>${esc(name)}</td><td>${s ? s.signals : 0}</td><td colspan="6" class="muted">${t("bt_no_fills")}</td></tr>`;
    const cls = s.total_r >= 0 ? "pos" : "neg";
    return `<tr><td>${esc(name)}</td><td>${s.signals}</td><td>${s.trades}</td><td>${fmt(s.win_rate_tp1, 1)}%</td>
      <td>${s.full_losses_pct == null ? "—" : fmt(s.full_losses_pct, 1) + "%"}</td><td class="${cls}">${fmt(s.avg_r, 2)}R</td><td class="${cls}">${fmt(s.total_r, 1)}R</td>
      <td>${s.profit_factor ?? "—"}</td></tr>`;
  }

  function renderBacktest() {
    const out = $("#bt");
    if (state.backtestError) {
      out.innerHTML = `<p class="muted">${esc(t("bt_failed", { msg: state.backtestError }))}</p>`;
      return;
    }
    const r = state.backtest;
    if (!r) return;
    const s = r.stats;
    const head = `<tr><th></th><th>${t("th_signals")}</th><th>${t("th_trades")}</th><th>${t("th_winrate")}</th><th>${t("th_full_losses")}</th>
      <th>${t("th_avg")}</th><th>${t("th_total")}</th><th>${t("th_pf")}</th></tr>`;
    const grades = ["all", "A+", "A", "B"].map((g) => statRow(g === "all" ? t("bt_all") : t("bt_grade", { g }), s[g])).join("");
    const names = Object.fromEntries(((state.status && state.status.strategies) || []).map((x) => [x.name, x]));
    const strat = Object.entries(s.by_strategy).map(([k, v]) => {
      const info = names[k];
      return statRow(info ? I18N.strategy(k, info.label, info.description).label : k, v);
    }).join("");
    const m = state.status && state.status.ml_model;
    const mlHtml = m ? `<h3 style="margin-top:14px">${esc(t("ml_heading", { a: localDate(m.test_period_from), b: localDate(m.data_to) }))}</h3>
      <div class="table-scroll"><table><thead>${head}</thead><tbody>
      ${statRow(t("ml_all"), { signals: m.test_all_candidates.trades, ...m.test_all_candidates, full_losses_pct: null })}
      ${statRow(t("ml_approved"), { signals: m.test_model_approved.trades, ...m.test_model_approved, full_losses_pct: null })}
      </tbody></table></div><p class="muted">${esc(t("ml_note", { auc: m.test_auc ?? "—", t: fmt(m.threshold * 100, 0), n: m.candidates }))}</p>` :
      `<p class="muted">${t("ml_none")}</p>`;
    out.innerHTML = `
      <p class="muted">${esc(t("bt_summary", { a: localDate(r.start), b: localDate(r.end), n: r.bars, dd: fmt(s.all.max_drawdown_r, 1) }))}</p>
      <div class="table-scroll"><table><thead>${head}</thead><tbody>${grades}</tbody></table></div>
      ${mlHtml}
      <h3 style="margin-top:14px">${t("bt_by_strategy")}</h3>
      <div class="table-scroll"><table><thead>${head}</thead><tbody>${strat}</tbody></table></div>`;
  }

  async function runBacktest() {
    $("#bt").innerHTML = `<p class="muted">${t("bt_running")}</p>`;
    try {
      state.backtest = await api("/api/backtest");
      state.backtestError = null;
      state.trades = state.backtest.trades;
      setMarkers();
    } catch (e) {
      state.backtestError = e.message;
    }
    renderBacktest();
  }

  function renderStatus() {
    const st = state.status;
    if (!st) return;
    const mlText = st.ml_model ? t("src_ml_on", { w: st.ml_model.test_model_approved.win_rate_tp1 ?? "—" }) : t("src_ml_off");
    const aiText = st.ai_provider ? t("src_ai", { p: st.ai_provider, m: st.ai_signal_mode }) : t("src_ai_off");
    $("#source").textContent = `${t("src_data", { p: st.provider })} · ${aiText} · ${mlText}`;
  }

  // fixed texts in the HTML (elements with data-i18n="key")
  function renderStatic() {
    document.documentElement.lang = I18N.lang;
    document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
    document.querySelectorAll(".lang button").forEach((b) => b.classList.toggle("active", b.dataset.lang === I18N.lang));
  }

  function renderAll() {
    renderStatic();
    renderStatus();
    renderAnalysis();
    renderNews();
    renderBacktest();
  }

  // ------------------------------------------------------------------ UI events
  document.querySelectorAll(".tf button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tf button").forEach((x) => x.classList.toggle("active", x === b));
    state.tf = b.dataset.tf;
    loadCandles(true);
  }));
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.id === `tab-${b.dataset.tab}`));
  }));
  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
    I18N.setLang(b.dataset.lang);
    renderAll();
  }));
  $("#run-bt").addEventListener("click", runBacktest);

  // ------------------------------------------------------------------ start
  (async () => {
    renderStatic();
    await loadStatus();
    await loadCandles(true);
    await loadAnalysis();
    loadNews();
    setInterval(() => { loadCandles(false); loadAnalysis(); }, 30000);
    setInterval(loadNews, 300000);
  })();
})();
