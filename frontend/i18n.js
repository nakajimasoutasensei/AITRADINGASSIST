/* Language support: English (en) and Bahasa Indonesia (id).
 *
 *  I18N.t(key, vars)  - text for the interface, e.g. t("score", { s: 72 })
 *  I18N.tr(message)   - translates a message that came from the server (strategy reasons, statuses, ...)
 *  I18N.lang / I18N.setLang("id")
 */
(() => {
  "use strict";

  const UI = {
    en: {
      loading: "loading…",
      legend_zone: "Entry zone",
      analysing: "Analysing…",
      why: "Why",
      context: "Market context",
      tab_votes: "Strategies",
      tab_news: "News",
      tab_calendar: "Calendar",
      tab_backtest: "Backtest",
      run_bt: "Run backtest on loaded data",
      footer: "Signals are for information only, not financial advice. Trading leveraged gold carries a high risk of loss.",
      cannot_load: "Cannot load data: {msg}",
      regime_trend_up: "Trending up",
      regime_trend_down: "Trending down",
      regime_range: "Ranging",
      regime_volatile: "Very volatile",
      age_min: "{n} min",
      age_h: "{n} h",
      age_days: "{n} days",
      updated: "Last candle {time} · {age} ago",
      market_closed: " (market closed or data delayed)",
      analysis_unavailable: "Analysis unavailable: {msg}",
      ai_confirmed: "AI confirmed this trade",
      ai_adjusted: "AI confirmed and adjusted the levels",
      ai_rejected: "AI rejected this trade",
      ai_analysing: "AI is analysing…",
      ai_error: "AI analyst unavailable — strategies only",
      ai_not_reviewed: "Not reviewed by AI",
      ai_signal: "Trade found by the AI analyst",
      levels_kept: "Levels kept from strategies: {p}",
      ai_scanning: "AI is scanning the market…",
      ai_no_trade_now: "no trade right now",
      no_trade: "No trade",
      waiting_setup: "Waiting for a good setup. Current reasons:",
      no_setup: "No setup on the latest candle",
      heading_rejected: "Rejected signal — no trade",
      heading_active: "Active signal",
      heading_finished: "Last signal (finished) — waiting for a new setup",
      who_ai: "found by the AI analyst",
      who_n: "{n} strategies agree",
      ml_prob: " · ML: {p}% chance of TP1",
      grade_title: "Signal grade",
      score: "Score {s}/100",
      kv_zone: "Entry zone",
      kv_entry: "Entry (limit)",
      kv_sl: "Stop loss",
      kv_tp1: "TP1 · close 50%",
      kv_tp2: "TP2 · close 30%",
      kv_tp3: "TP3 · runner",
      kv_rr: "Risk : reward (TP2)",
      kv_lot: "Lot size",
      kv_lot_val: "{lot} lot (≈ ${usd} risk)",
      kv_valid: "Valid until",
      engine_levels: "Strategy levels before AI: SL {sl} · TP1 {tp1} · zone {z}",
      status: "Status",
      no_votes: "No active strategy votes right now.",
      bullish: "bullish",
      bearish: "bearish",
      neutral: "neutral",
      unavailable: "unavailable",
      ctx_news: "News bias for gold",
      ctx_dollar: "Dollar & yields bias",
      ctx_dxy: "US Dollar Index (24h)",
      ctx_us10y: "US 10Y yield (24h)",
      ctx_strength: "Buy / sell strength",
      ctx_pd: "Previous day high / low",
      ctx_asia: "Asian range",
      ctx_atr: "ATR (15m)",
      th_vote: "Vote",
      th_strategy: "Strategy",
      th_confidence: "Confidence",
      th_zone: "Zone",
      idle: "idle",
      news_bias: "News bias: {b} · analysed by {m}",
      no_headlines: "No headlines loaded (check internet connection).",
      cal_intro: "USD events. New signals are blocked 30 minutes before and after High-impact news.",
      th_time: "Time",
      th_impact: "Impact",
      th_event: "Event",
      th_fp: "Forecast / Previous",
      cal_fp: "F: {f} · P: {p}",
      impact_High: "High",
      impact_Medium: "Medium",
      no_events: "No upcoming events loaded.",
      bt_running: "Running…",
      th_signals: "Signals",
      th_trades: "Trades",
      th_winrate: "Win rate (TP1)",
      th_full_losses: "Full losses",
      th_avg: "Avg",
      th_total: "Total",
      th_pf: "Profit factor",
      bt_all: "All signals",
      bt_grade: "Grade {g}",
      bt_no_fills: "no filled trades",
      ml_heading: "ML model — test on unseen data ({a} → {b})",
      ml_all: "All candidates",
      ml_approved: "Approved by model",
      ml_note: "AUC {auc} (0.5 = no skill) · threshold {t}% · trained on {n} candidate trades.",
      ml_none: "No ML model trained yet. Run <code>python -m backend.app.ml --csv your_history.csv</code>.",
      bt_summary: "{a} → {b} · {n} candles · max drawdown {dd}R. Arrows on the chart show each trade. Results include spread; news filters are not applied in backtests.",
      bt_by_strategy: "By strategy (trades where it agreed)",
      bt_failed: "Backtest failed: {msg}",
      src_data: "Data: {p}",
      src_ml_on: "ML filter on (test win rate {w}%)",
      src_ml_off: "ML filter off",
      src_ai: "AI: {p} ({m})",
      src_ai_off: "AI: off (no API key)",
      zone_label: "{dir} ZONE {lo}–{hi}",
      lang_label: "Language",
    },
    id: {
      loading: "memuat…",
      legend_zone: "Zona entry",
      analysing: "Menganalisis…",
      why: "Alasan",
      context: "Kondisi pasar",
      tab_votes: "Strategi",
      tab_news: "Berita",
      tab_calendar: "Kalender",
      tab_backtest: "Backtest",
      run_bt: "Jalankan backtest pada data yang dimuat",
      footer: "Sinyal hanya untuk informasi, bukan nasihat keuangan. Trading emas dengan leverage berisiko tinggi kehilangan uang.",
      cannot_load: "Data tidak bisa dimuat: {msg}",
      regime_trend_up: "Tren naik",
      regime_trend_down: "Tren turun",
      regime_range: "Sideways",
      regime_volatile: "Sangat volatil",
      age_min: "{n} menit",
      age_h: "{n} jam",
      age_days: "{n} hari",
      updated: "Candle terakhir {time} · {age} lalu",
      market_closed: " (pasar tutup atau data terlambat)",
      analysis_unavailable: "Analisis tidak tersedia: {msg}",
      ai_confirmed: "AI menyetujui trade ini",
      ai_adjusted: "AI menyetujui dan menyesuaikan level",
      ai_rejected: "AI menolak trade ini",
      ai_analysing: "AI sedang menganalisis…",
      ai_error: "Analis AI tidak tersedia — hanya strategi",
      ai_not_reviewed: "Belum diperiksa AI",
      ai_signal: "Trade ditemukan oleh analis AI",
      levels_kept: "Level dari strategi tetap dipakai: {p}",
      ai_scanning: "AI sedang memindai pasar…",
      ai_no_trade_now: "belum ada trade",
      no_trade: "Tidak ada trade",
      waiting_setup: "Menunggu setup yang bagus. Alasan saat ini:",
      no_setup: "Tidak ada setup di candle terakhir",
      heading_rejected: "Sinyal ditolak — tidak ada trade",
      heading_active: "Sinyal aktif",
      heading_finished: "Sinyal terakhir (selesai) — menunggu setup baru",
      who_ai: "ditemukan oleh analis AI",
      who_n: "{n} strategi setuju",
      ml_prob: " · ML: peluang TP1 {p}%",
      grade_title: "Grade sinyal",
      score: "Skor {s}/100",
      kv_zone: "Zona entry",
      kv_entry: "Entry (limit)",
      kv_sl: "Stop loss",
      kv_tp1: "TP1 · tutup 50%",
      kv_tp2: "TP2 · tutup 30%",
      kv_tp3: "TP3 · sisa posisi",
      kv_rr: "Risk : reward (TP2)",
      kv_lot: "Ukuran lot",
      kv_lot_val: "{lot} lot (risiko ≈ ${usd})",
      kv_valid: "Berlaku sampai",
      engine_levels: "Level strategi sebelum AI: SL {sl} · TP1 {tp1} · zona {z}",
      status: "Status",
      no_votes: "Belum ada strategi yang aktif saat ini.",
      bullish: "bullish",
      bearish: "bearish",
      neutral: "netral",
      unavailable: "tidak tersedia",
      ctx_news: "Arah berita untuk emas",
      ctx_dollar: "Arah dollar & yield",
      ctx_dxy: "Indeks Dollar AS (24 jam)",
      ctx_us10y: "Yield obligasi AS 10 th (24 jam)",
      ctx_strength: "Kekuatan buy / sell",
      ctx_pd: "High / low hari sebelumnya",
      ctx_asia: "Range sesi Asia",
      ctx_atr: "ATR (15m)",
      th_vote: "Suara",
      th_strategy: "Strategi",
      th_confidence: "Keyakinan",
      th_zone: "Zona",
      idle: "pasif",
      news_bias: "Arah berita: {b} · dianalisis oleh {m}",
      no_headlines: "Belum ada berita (cek koneksi internet).",
      cal_intro: "Jadwal berita ekonomi USD. Sinyal baru diblokir 30 menit sebelum dan sesudah berita berdampak tinggi.",
      th_time: "Waktu",
      th_impact: "Dampak",
      th_event: "Peristiwa",
      th_fp: "Perkiraan / Sebelumnya",
      cal_fp: "Perk.: {f} · Sblm.: {p}",
      impact_High: "Tinggi",
      impact_Medium: "Sedang",
      no_events: "Belum ada jadwal berita.",
      bt_running: "Sedang berjalan…",
      th_signals: "Sinyal",
      th_trades: "Trade",
      th_winrate: "Win rate (TP1)",
      th_full_losses: "Kalah penuh",
      th_avg: "Rata-rata",
      th_total: "Total",
      th_pf: "Profit factor",
      bt_all: "Semua sinyal",
      bt_grade: "Grade {g}",
      bt_no_fills: "tidak ada trade yang terisi",
      ml_heading: "Model ML — uji pada data yang belum pernah dilihat ({a} → {b})",
      ml_all: "Semua kandidat",
      ml_approved: "Disetujui model",
      ml_note: "AUC {auc} (0,5 = tidak ada keunggulan) · ambang {t}% · dilatih dengan {n} kandidat trade.",
      ml_none: "Model ML belum dilatih. Jalankan <code>python -m backend.app.ml --csv histori_kamu.csv</code>.",
      bt_summary: "{a} → {b} · {n} candle · drawdown maksimum {dd}R. Panah di chart menunjukkan tiap trade. Hasil sudah termasuk spread; filter berita tidak dipakai di backtest.",
      bt_by_strategy: "Per strategi (trade yang disetujui strategi itu)",
      bt_failed: "Backtest gagal: {msg}",
      src_data: "Data: {p}",
      src_ml_on: "Filter ML aktif (win rate uji {w}%)",
      src_ml_off: "Filter ML mati",
      src_ai: "AI: {p} ({m})",
      src_ai_off: "AI: mati (tidak ada API key)",
      zone_label: "ZONA {dir} {lo}–{hi}",
      lang_label: "Bahasa",
    },
  };

  // strategy names and descriptions (keyed by the server's strategy name)
  const STRATEGY_ID = {
    trend_pullback: ["Pullback tren multi-timeframe", "Tren EMA di 4h + 1h searah; entry saat pullback 15m ke EMA20/50"],
    structure_ob: ["Break of structure + order block", "Close menembus swing terakhir, lalu retest pertama ke order block"],
    fvg: ["Fair value gap", "Harga kembali pertama kali ke celah ketidakseimbangan 3 candle"],
    liquidity_sweep: ["Liquidity sweep", "Stop hunt melewati level swing / hari sebelumnya / Asia, lalu ditutup kembali ke dalam"],
    key_levels: ["Level kunci", "Rejection di angka bulat $25 atau high/low/close hari sebelumnya"],
    session_breakout: ["Breakout sesi", "Breakout range Asia saat sesi London / NY, buy/sell saat retest"],
    squeeze: ["Squeeze volatilitas", "Bollinger di dalam Keltner, lalu melebar dengan momentum"],
    fib: ["Zona emas Fibonacci", "Pullback searah tren ke retracement 50-70,5%"],
    mean_reversion: ["Mean reversion", "RSI ekstrem di luar Bollinger Band, lalu kembali ke dalam (hanya saat sideways)"],
    divergence: ["Divergence RSI", "Lower low / higher high yang tidak dikonfirmasi RSI"],
  };

  const LEVEL_ID = {
    "swing low": "swing low", "swing high": "swing high",
    "previous day low": "low hari sebelumnya", "previous day high": "high hari sebelumnya",
    "previous day close": "close hari sebelumnya",
    "Asian low": "low Asia", "Asian high": "high Asia",
  };
  const levelNames = (s) => s.split(", ").map((n) => {
    const m = n.match(/^round number (\d+)$/);
    return m ? `angka bulat ${m[1]}` : LEVEL_ID[n] || n;
  }).join(", ");
  const dec = (s) => s.replace(".", ",");

  // messages generated by the server -> Indonesian
  const MESSAGES_ID = [
    // strategy reasons
    [/^4h \+ 1h uptrend, 15m pulled back to EMA20\/50 and bounced$/, "Tren naik di 4h + 1h, harga 15m pullback ke EMA20/50 lalu memantul"],
    [/^4h \+ 1h downtrend, 15m pulled back to EMA20\/50 and rejected$/, "Tren turun di 4h + 1h, harga 15m pullback ke EMA20/50 lalu tertolak"],
    [/^Broke above Asian range high ([\d.]+); buy the retest$/, "Menembus high range Asia $1; buy saat retest"],
    [/^Broke below Asian range low ([\d.]+); sell the retest$/, "Menembus low range Asia $1; sell saat retest"],
    [/^Volatility squeeze released upward with rising momentum$/, "Squeeze volatilitas pecah ke atas dengan momentum naik"],
    [/^Volatility squeeze released downward with falling momentum$/, "Squeeze volatilitas pecah ke bawah dengan momentum turun"],
    [/^Bullish break of structure above ([\d.]+), retest of order block$/, "Break of structure bullish di atas $1, retest order block"],
    [/^Bearish break of structure below ([\d.]+), retest of order block$/, "Break of structure bearish di bawah $1, retest order block"],
    [/^Price returned into (bullish|bearish) fair value gap (.+)$/, "Harga kembali ke fair value gap $1 $2"],
    [/^Swept liquidity below (.+?) ([\d.]+) and closed back above$/, (m, a, b) => `Menyapu likuiditas di bawah ${levelNames(a)} ${b} lalu ditutup kembali di atasnya`],
    [/^Swept liquidity above (.+?) ([\d.]+) and closed back below$/, (m, a, b) => `Menyapu likuiditas di atas ${levelNames(a)} ${b} lalu ditutup kembali di bawahnya`],
    [/^(Bullish|Bearish) rejection at (.+)$/, (m, a, b) => `Rejection ${a.toLowerCase()} di ${levelNames(b)}`],
    [/^Pullback into 50-70\.5% Fibonacci zone of the (.+?) rally$/, "Pullback ke zona Fibonacci 50-70,5% dari kenaikan $1"],
    [/^Pullback into 50-70\.5% Fibonacci zone of the (.+?) drop$/, "Pullback ke zona Fibonacci 50-70,5% dari penurunan $1"],
    [/^Oversold \(RSI < 30\) below lower Bollinger Band, closed back inside; target VWAP \/ mid-band$/,
      "Oversold (RSI < 30) di bawah Bollinger Band bawah, lalu ditutup kembali di dalam; target VWAP / garis tengah"],
    [/^Overbought \(RSI > 70\) above upper Bollinger Band, closed back inside; target VWAP \/ mid-band$/,
      "Overbought (RSI > 70) di atas Bollinger Band atas, lalu ditutup kembali di dalam; target VWAP / garis tengah"],
    [/^Bullish RSI divergence: lower low ([\d.]+) with higher RSI$/, "Divergence RSI bullish: lower low $1 dengan RSI lebih tinggi"],
    [/^Bearish RSI divergence: higher high ([\d.]+) with lower RSI$/, "Divergence RSI bearish: higher high $1 dengan RSI lebih rendah"],
    // why a signal is blocked
    [/^Only (\d+) strategy\(ies\) agree \(need (\d+)\)$/, "Baru $1 strategi yang setuju (butuh $2)"],
    [/^Score (\d+) below (\d+)$/, "Skor $1 di bawah $2"],
    [/^Extreme volatility: standing aside$/, "Volatilitas ekstrem: tidak trading dulu"],
    [/^Sunday open: thin liquidity$/, "Pembukaan hari Minggu: likuiditas tipis"],
    [/^Friday close: weekend gap risk$/, "Penutupan Jumat: risiko gap akhir pekan"],
    [/^Daily rollover: wide spreads$/, "Rollover harian: spread lebar"],
    [/^High-impact news: (.+) at (\d\d:\d\d) UTC$/, "Berita berdampak tinggi: $1 pukul $2 UTC"],
    [/^Stop loss would be too wide for this setup$/, "Stop loss terlalu lebar untuk setup ini"],
    [/^ML model: (\d+)% chance of reaching TP1 \(needs (\d+)%\)$/, "Model ML: peluang kena TP1 $1% (butuh $2%)"],
    [/^News bias is against this trade$/, "Arah berita berlawanan dengan trade ini"],
    [/^News bias supports this trade$/, "Arah berita mendukung trade ini"],
    [/^Dollar & yields bias is against this trade$/, "Arah dollar & yield berlawanan dengan trade ini"],
    [/^Dollar & yields bias supports this trade$/, "Arah dollar & yield mendukung trade ini"],
    // trade status
    [/^expired \(entry zone not reached\)$/, "kedaluwarsa (zona entry tidak tersentuh)"],
    [/^missed \(TP1 reached before entry\)$/, "terlewat (TP1 tercapai sebelum entry)"],
    [/^closed after 24 hours$/, "ditutup setelah 24 jam"],
    [/^stopped out$/, "kena stop loss"],
    [/^closed at break-even$/, "ditutup di break-even"],
    [/^closed after TP(\d)$/, "ditutup setelah TP$1"],
    [/^TP3 hit - trade complete$/, "TP3 tercapai - trade selesai"],
    [/^waiting for price to reach the entry zone$/, "menunggu harga masuk zona entry"],
    [/^in trade$/, "posisi berjalan"],
    [/^TP(\d) hit - stop moved to break-even$/, "TP$1 tercapai - stop dipindah ke break-even"],
    [/^TP(\d) hit - stop moved to TP1$/, "TP$1 tercapai - stop dipindah ke TP1"],
    [/^rejected by the AI analyst$/, "ditolak oleh analis AI"],
    // AI level safety checks
    [/^levels are not in the right order$/, "urutan level tidak benar"],
    [/^stop distance ([\d.]+) is outside 0\.6-4 ATR$/, (m, a) => `jarak stop ${dec(a)} di luar 0,6-4 ATR`],
    [/^entry zone wider than 1\.5 ATR$/, "zona entry lebih lebar dari 1,5 ATR"],
    [/^entry zone too far from the current price$/, "zona entry terlalu jauh dari harga sekarang"],
    [/^TP1 is less than 0\.5R away$/, "TP1 kurang dari 0,5R dari entry"],
    // news keyword model
    [/^keyword model \((\d+) bullish \/ (\d+) bearish terms\)$/, "model kata kunci ($1 kata bullish / $2 kata bearish)"],
    [/^keyword model$/, "model kata kunci"],
  ];

  const STORE_KEY = "xauusd-lang";
  let lang = "en";
  try {
    lang = localStorage.getItem(STORE_KEY) || ((navigator.language || "").toLowerCase().startsWith("id") ? "id" : "en");
  } catch (_) {
    lang = (navigator.language || "").toLowerCase().startsWith("id") ? "id" : "en";
  }
  if (!UI[lang]) lang = "en";

  function t(key, vars) {
    let s = (UI[lang] && UI[lang][key]) ?? UI.en[key] ?? key;
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
    return s;
  }

  function tr(msg) {
    if (lang !== "id" || msg == null) return msg;
    for (const [re, rep] of MESSAGES_ID) {
      if (re.test(msg)) return msg.replace(re, rep);
    }
    return msg;
  }

  function strategy(name, label, description) {
    const s = lang === "id" && STRATEGY_ID[name];
    return s ? { label: s[0], description: s[1] } : { label, description };
  }

  // pick the AI's Indonesian text when available (older answers may only have English)
  function aiText(obj, field) {
    if (!obj) return field === "summary" ? "" : [];
    const local = lang === "id" ? obj[`${field}_id`] : null;
    const hasLocal = Array.isArray(local) ? local.length > 0 : !!local;
    return hasLocal ? local : obj[field];
  }

  function setLang(l) {
    if (!UI[l]) return;
    lang = l;
    try { localStorage.setItem(STORE_KEY, l); } catch (_) { /* private mode: not remembered */ }
  }

  window.I18N = {
    t, tr, strategy, aiText, setLang,
    get lang() { return lang; },
    get locale() { return lang === "id" ? "id-ID" : undefined; },
  };
})();
