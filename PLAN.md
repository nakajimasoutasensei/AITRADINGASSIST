# AI Trading Assist — XAUUSD (Gold) Project Plan

An AI-assisted trading platform for **XAUUSD**. Instead of relying on one strategy, it runs
**many strategies at the same time**, reads **news and macro data**, and combines everything
into one decision. A web dashboard shows the live chart with:

- a shaded **BUY zone** or **SELL zone** (where to enter)
- a **Stop Loss (SL)** line
- **Take Profit (TP1 / TP2 / TP3)** lines
- a **confidence score** and a plain-language **explanation** of why the signal exists

> **Note on "high win rate":** win rate alone does not make a system profitable. A 90% win
> rate with tiny wins and huge losses still loses money. This plan aims for a high win rate
> **and** positive expectancy by (1) only taking trades where many strategies agree,
> (2) skipping bad conditions (news spikes, wide spreads, unclear regime), and (3) using
> partial take-profits so most trades lock in a gain early. Nothing here guarantees profit;
> everything must be proven in backtests and paper trading before real money is used.

---

## 1. How it works (big picture)

```
 ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ Price data   │   │ News & macro │   │ Intermarket  │
 │ XAUUSD M1–D1 │   │ calendar,    │   │ DXY, US10Y,  │
 │ (live+history│   │ headlines,   │   │ real yields, │
 │              │   │ Fed speakers │   │ SPX, silver  │
 └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
        │                  │                  │
        ▼                  ▼                  ▼
 ┌─────────────────────────────────────────────────────┐
 │ 1. Regime detector  (trending / ranging / volatile) │
 └─────────────────────────┬───────────────────────────┘
                           ▼
 ┌─────────────────────────────────────────────────────┐
 │ 2. Strategy ensemble (10+ strategies run in parallel)│
 │    each votes: direction, entry zone, confidence     │
 └─────────────────────────┬───────────────────────────┘
                           ▼
 ┌─────────────────────────────────────────────────────┐
 │ 3. AI layer                                          │
 │    • News AI (LLM) → sentiment, event risk, bias     │
 │    • Meta-model (ML) → probability TP1 hit before SL │
 └─────────────────────────┬───────────────────────────┘
                           ▼
 ┌─────────────────────────────────────────────────────┐
 │ 4. Risk engine → entry zone, SL, TP1/2/3, lot size,  │
 │    filters (news blackout, spread, daily loss limit) │
 └─────────────────────────┬───────────────────────────┘
                           ▼
 ┌─────────────────────────────────────────────────────┐
 │ 5. Web dashboard (chart + zones + TP/SL + reasons)   │
 │    optional: auto-execution via broker (later phase) │
 └─────────────────────────────────────────────────────┘
```

---

## 2. Data sources

| Data | Purpose | Options |
|---|---|---|
| XAUUSD candles (M1, M5, M15, H1, H4, D1) | All strategies, backtesting | MetaTrader 5 (Python `MetaTrader5` package), OANDA v20 API, Twelve Data, Polygon, Dukascopy (free tick history) |
| Live ticks / spread | Entry timing, spread filter | Broker feed (MT5 / OANDA) |
| Economic calendar | Know when CPI, NFP, FOMC, PCE, GDP, jobless claims land | Forex Factory, Trading Economics API, Finnhub |
| News headlines | Sentiment & event risk | Finnhub, NewsAPI, Benzinga, RSS (Reuters, Kitco, FXStreet), Fed/Treasury press releases |
| Intermarket | Gold's main drivers | DXY (US Dollar Index), US 10Y yield, 10Y TIPS (real yield), S&P 500, XAGUSD (silver), VIX |
| Positioning (optional) | Longer-term bias | CFTC Commitment of Traders (weekly), gold ETF flows (GLD holdings) |

Everything is stored in a time-series database so the exact same data powers backtests and live signals.

---

## 3. The strategies (the "many strategies" part)

Each strategy is a small, independent module with the same interface:

```python
class Strategy:
    name: str
    def evaluate(self, market: MarketSnapshot) -> Vote | None:
        # returns direction (BUY/SELL), entry zone (low, high),
        # invalidation level (for SL), target levels, confidence 0–1
```

| # | Strategy | Idea | Best regime |
|---|---|---|---|
| 1 | **Multi-timeframe trend** | EMA 20/50/200 aligned on H4 + H1, enter on M15 pullback | Trending |
| 2 | **Market structure (SMC)** | Break of structure / change of character, enter on order block | Trending |
| 3 | **Fair value gaps** | Price returns to fill an imbalance gap, then continues | Trending |
| 4 | **Liquidity sweep reversal** | Stop-hunt above/below previous high/low, then sharp rejection | Ranging / reversal |
| 5 | **Supply & demand zones** | Fresh zones where price left with strong momentum | Any |
| 6 | **Key levels & round numbers** | Gold respects $10 / $25 / $50 / $100 levels, previous day/week high & low | Any |
| 7 | **Session breakouts** | Asian range breakout at London open; NY open continuation/reversal | Session opens |
| 8 | **Mean reversion** | Bollinger Band / RSI extremes + VWAP reversion | Ranging |
| 9 | **Divergence** | RSI/MACD divergence at key levels | Exhaustion |
| 10 | **Volatility squeeze breakout** | Bollinger inside Keltner (squeeze) → expansion | Low → high volatility |
| 11 | **Fibonacci confluence** | 0.5 / 0.618 / 0.705 retracement overlapping another zone | Trending pullbacks |
| 12 | **Intermarket bias** | Falling DXY & real yields = gold bullish bias (and vice versa) | Filter / bias |
| 13 | **News / macro bias** | AI-read news + calendar outcome (e.g. CPI below forecast → bullish gold) | Around events |

### Regime detection
Not every strategy works in every market. A regime detector classifies the market as
**trending up / trending down / ranging / high-volatility chaos** using ADX, ATR percentile,
EMA slope and (later) a Hidden Markov Model. Each strategy's vote is **weighted by how well
it historically performs in the current regime**. In "chaos" (e.g. right after NFP) the
system stands aside.

---

## 4. The AI layer

### 4a. News AI (LLM)
An LLM (e.g. Claude via the Anthropic API) reads every new headline and calendar result and returns structured output:

```json
{
  "headline": "US CPI rises 0.1% vs 0.3% expected",
  "impact_on_gold": "bullish",
  "strength": 0.8,
  "time_horizon": "hours",
  "reason": "Softer inflation → higher odds of Fed cuts → lower real yields → gold up",
  "event_risk": "high"
}
```

- Cheap/fast model for triaging hundreds of headlines; stronger model for important events.
- Produces a rolling **news bias score** (−1 bearish … +1 bullish) and an **event-risk flag**.
- Also writes the human-readable explanation shown on the dashboard for each signal.
- The LLM is **not** asked to guess prices — it interprets news. Price logic stays in the strategies and the ML model, which are testable.

### 4b. Meta-model (machine learning)
This is what pushes win rate up. For every historical moment where strategies voted, we record:

- which strategies voted and their confidence
- regime, session, ATR, spread, distance to key levels
- news bias, minutes to next high-impact event
- intermarket readings (DXY, yields)
- **outcome:** did price hit TP1 before SL?

A gradient-boosting model (LightGBM / XGBoost) learns **which combinations actually win**.
Live, it outputs a probability, e.g. *"72% chance TP1 is hit before SL"*. A signal is only
shown when probability ≥ threshold (start at ~65%, tune in backtests).

### 4c. Final signal score
```
score = meta_model_probability
        × regime_fit
        × news_alignment     (penalise trades against strong news bias)
        × (no high-impact event in next 30 min)
```
Signal grades: **A+** (very strong), **A**, **B** (shown but not recommended), below B = hidden.

---

## 5. Entry zone, Stop Loss and Take Profit

| Item | How it is calculated |
|---|---|
| **Entry zone** | The overlap of the zones from agreeing strategies (e.g. order block ∩ 0.618 fib ∩ round number). Drawn as a shaded box. |
| **Stop Loss** | Just beyond the structure that invalidates the idea (zone edge / swing high-low) + buffer of `0.3 × ATR` + spread. Hard max distance so risk never gets too large. |
| **TP1** | ~1R or nearest opposing level (whichever is closer). Close 50%, move SL to breakeven. |
| **TP2** | ~2R or next key level. Close 30%. |
| **TP3** | Runner: trailing stop (ATR or structure) toward the next major level. |
| **Position size** | `lot = (account × risk%) / (SL distance × contract value)`; default risk 0.5–1% per trade. |

Because TP1 is close and the stop moves to breakeven, most qualified trades finish as a win
or breakeven — that is how the win rate is kept high **without** risking big losses for small gains.

### Safety filters (trade is blocked if any is true)
- High-impact news within ±30 minutes (CPI, NFP, FOMC, PCE, Fed Chair speech)
- Spread above normal (e.g. > 2× median)
- Daily loss limit reached (e.g. −2% for the day) or 3 losses in a row
- Friday late session / weekend gap risk
- Strategies strongly disagree (high conflict score)

---

## 6. Web dashboard

```
┌─────────────────────────────────────────────────────────────┬───────────────────────┐
│ XAUUSD  M15 ▾   2,418.35  ▲0.42%      Regime: TRENDING UP   │ ACTIVE SIGNAL     A+  │
│─────────────────────────────────────────────────────────────│ BUY  XAUUSD           │
│                                         ── TP3 2,441.00 ─── │ Entry  2,412 – 2,415  │
│                                         ── TP2 2,432.00 ─── │ SL     2,405.50       │
│            ╱╲      ╱╲                   ── TP1 2,424.00 ─── │ TP1/2/3 2,424 / 2,432 │
│      ╱╲  ╱    ╲  ╱    ╲   ╱                                 │        / 2,441        │
│    ╱    ╲       ╲╱      ╲╱                                  │ Probability   74%     │
│  ╱               ░░░░░░░░░░░░░░░░ BUY ZONE 2,412–2,415      │ R:R (TP2)     1:2.1   │
│                  ░░░░░░░░░░░░░░░░                           │ Lot (1% risk) 0.15    │
│                 - - - - - - - - - SL 2,405.50 - - - - -     │───────────────────────│
│                                                             │ WHY                   │
│─────────────────────────────────────────────────────────────│ ✔ H4 + H1 uptrend     │
│ RSI / volume / strategy-agreement heatmap                   │ ✔ Bullish order block │
├─────────────────────────────────────────────────────────────┤ ✔ 0.618 fib + $2,415  │
│ NEWS  🟢 CPI below forecast → bullish (0.8)                 │ ✔ DXY falling         │
│       🟡 Fed speaker 18:00 → event risk                      │ ✔ News bias bullish   │
│ CALENDAR  NFP Fri 12:30 UTC  ⚠ trading paused ±30 min       │ ✖ Asian session low   │
│                                                             │   volume (minor)      │
└─────────────────────────────────────────────────────────────┴───────────────────────┘
```

Features:
- **TradingView Lightweight Charts** with custom drawings: zone boxes, SL/TP lines, markers for past signals
- Live updates over WebSocket (new candle, new signal, TP/SL hit)
- Signal panel: direction, zone, SL, TP1–3, probability, R:R, lot size calculator
- "Why" list: each strategy that agreed / disagreed
- News feed with AI sentiment colour + economic calendar with blackout windows
- **Journal & stats page:** every signal, result, win rate, profit factor, drawdown, per-strategy performance
- Alerts: browser push, Telegram and/or Discord when an A/A+ signal appears

---

## 7. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, WebSockets |
| Analysis | pandas, numpy, pandas-ta / TA-Lib |
| ML | LightGBM, scikit-learn, Optuna (tuning) |
| LLM | Anthropic API (Claude) for news interpretation & explanations |
| Scheduling / jobs | APScheduler or Celery + Redis |
| Database | PostgreSQL + TimescaleDB (candles, signals, trades, news) |
| Frontend | Next.js (React) + TypeScript + TradingView Lightweight Charts + Tailwind |
| Broker / execution (later) | MetaTrader 5 Python bridge or OANDA v20 API |
| Alerts | Telegram Bot API, Discord webhook |
| Deploy | Docker Compose → VPS (low latency to broker) |

### Proposed folder structure
```
AITRADINGASSIST/
├── backend/
│   ├── data/            # feeds: prices, news, calendar, intermarket
│   ├── regime/          # regime detector
│   ├── strategies/      # one file per strategy (common interface)
│   ├── ai/              # news LLM, meta-model training & inference
│   ├── risk/            # zones, SL/TP, position sizing, filters
│   ├── signals/         # ensemble aggregator → final signal
│   ├── backtest/        # event-driven backtester, walk-forward, Monte Carlo
│   ├── execution/       # (phase 6) broker connectors
│   └── api/             # FastAPI routes + WebSocket
├── frontend/            # Next.js dashboard
├── notebooks/           # research
├── docker-compose.yml
└── PLAN.md
```

---

## 8. Testing & validation (the most important part)

1. **Clean historical data** — at least 5–10 years of M1/M5 XAUUSD (includes 2020 crash, 2022 hikes, 2024–25 rally).
2. **Realistic costs** — spread, commission, slippage (bigger around news).
3. **No look-ahead bias** — strategies only see closed candles; news only after its timestamp.
4. **Walk-forward testing** — train on years 1–3, test on year 4, roll forward. Never tune on the test set.
5. **Monte Carlo** — shuffle trade order to estimate worst-case drawdown.
6. **Per-strategy report** — drop strategies that don't add value to the ensemble.
7. **Paper trading** — 4–8 weeks live on a demo account; live results must match backtest within reason.
8. **Small live** — minimum size before scaling.

### Target metrics (to be confirmed by backtests)
| Metric | Target |
|---|---|
| Win rate (TP1 hit) | 65 – 75% |
| Profit factor | > 1.5 |
| Max drawdown | < 10% |
| Avg R per trade | > +0.3R |
| Signals per day | 1 – 4 quality signals (quality over quantity) |

---

## 9. Roadmap

| Phase | Deliverable | Est. time |
|---|---|---|
| **0. Setup** | Repo, Docker, DB, choose data provider & broker | 1 week |
| **1. Data** | Historical + live candles, intermarket feeds, economic calendar, news ingestion | 1–2 weeks |
| **2. Chart dashboard (MVP)** | Live XAUUSD chart in browser, can draw zones/lines manually from API | 1–2 weeks |
| **3. Strategies + backtester** | First 6 strategies, regime detector, event-driven backtester with costs | 3–4 weeks |
| **4. AI layer** | News LLM sentiment, meta-model training, scoring, explanations | 2–3 weeks |
| **5. Signals live** | Ensemble → zones + SL/TP on chart, alerts, journal & stats; remaining strategies | 2–3 weeks |
| **6. Paper trading** | Run on demo, compare to backtest, tune thresholds | 4–8 weeks |
| **7. (Optional) Auto-execution** | MT5/OANDA order placement with all risk limits + kill switch | 2 weeks |
| **8. Ongoing** | Monthly retraining, strategy health monitoring, auto-disable decaying strategies | continuous |

---

### Progress

- [x] Phase 0–1: data sources (yfinance, Twelve Data, MT5, CSV, synthetic), economic calendar, news feeds, dollar/yields
- [x] Phase 2: live chart dashboard with entry zone, SL/TP lines, signal card, reasons, news, calendar
- [x] Phase 3: 10 strategies, regime detector, bar-by-bar backtester with spread and partial take-profits
- [x] Phase 4: news AI (Claude or keyword fallback), Claude AI analyst for signals (review / full mode),
      ML meta-model (training pipeline with honest out-of-sample report; needs multi-year data to be useful)
- [ ] Phase 5: Telegram/Discord alerts, journal
- [ ] Phase 6: paper trading on a demo account and tuning on real history
- [ ] Phase 7: optional auto-execution

MVP decisions (can be changed later): signals only, intraday (15m entries with 1h/4h trend),
simple HTML/JS frontend served by FastAPI instead of Next.js, polling every 30 s instead of WebSockets.

---

## 10. Risks & how we handle them

| Risk | Mitigation |
|---|---|
| Overfitting (great backtest, bad live) | Walk-forward, out-of-sample, limit parameters, paper trade first |
| News spikes / slippage | Blackout windows, spread filter, smaller size near events |
| LLM misreads news | Structured outputs, confidence threshold, LLM is only one input, logs reviewed |
| Strategy decay over time | Rolling performance tracking, auto-reduce weight of underperformers |
| Data feed outage | Fallback provider, stale-data detection → stop signals |
| Over-trading / emotional use | Daily loss limit, max trades per day, only A/A+ signals highlighted |

---

## 11. Decisions needed before building

1. **Broker / data source** — MT5 (which broker?), OANDA, or another?
2. **Trading style** — scalping (M1–M5), intraday (M15–H1), or swing (H4–D1)? This changes timeframes, TP/SL sizes and strategy weights.
3. **Signals only, or auto-trading?** — Plan assumes signals first, auto-execution optional later.
4. **Budget for paid APIs** — news/calendar feeds and LLM calls (roughly $20–150/month depending on volume).
5. **Alerts** — Telegram, Discord, email, or browser only?

> Disclaimer: this is a software plan, not financial advice. Trading gold on leverage carries
> a high risk of loss.
