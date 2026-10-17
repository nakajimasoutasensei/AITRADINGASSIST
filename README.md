# AI Trading Assist — XAUUSD

A web dashboard that analyses gold (XAUUSD) with **10 strategies at once**, reads **news and the
economic calendar**, checks the **US dollar and bond yields**, and shows on a live chart:

- a shaded **BUY / SELL entry zone**
- **Stop Loss** and **TP1 / TP2 / TP3** lines
- a grade (**A+ / A / B**), a score, the lot size for your risk, and the reasons behind the signal
- a **backtest** of the same rules on the loaded history, with arrows on the chart for every past trade

See [PLAN.md](PLAN.md) for the full design and roadmap.

> Signals are for information only and are not financial advice. Test on a demo account first.

## Quick start (Windows)

1. Install **Python 3.11+** from [python.org](https://www.python.org/downloads/) (tick *Add Python to PATH*).
2. Download this repository and double-click **`start.bat`**.
3. Your browser opens **http://127.0.0.1:8000**.

The first start installs the packages and creates a `.env` settings file.

## Quick start (Mac / Linux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.app.main:app --port 8000
```

## Settings (`.env`)

| Setting | What it does |
|---|---|
| `DATA_PROVIDER` | `yfinance` (free, default, uses gold futures `GC=F` which are a few $ above spot), `twelvedata` (real XAU/USD spot, free key at twelvedata.com), `mt5` (your MetaTrader 5 terminal, Windows: also `pip install MetaTrader5`), `synthetic` (fake data for testing) |
| `TWELVEDATA_API_KEY` | needed for `twelvedata` |
| `MT5_SYMBOL`, `MT5_UTC_OFFSET` | broker symbol name (e.g. `XAUUSD`, `XAUUSDm`) and the broker server's UTC offset in hours |
| `ANTHROPIC_API_KEY` | optional: lets Claude read the news. Without it a simple keyword model is used |
| `CLAUDE_MODEL` | default `claude-opus-5-5` |
| `ACCOUNT_BALANCE`, `RISK_PERCENT` | used for the lot-size calculator (default $1000, 1%) |
| `SPREAD` | spread in $ added to stop losses and charged in backtests (default 0.30) |

## How a signal is made

1. **Data**: 15-minute candles; 1-hour, 4-hour and daily context is built from them. Every value only uses
   candles that had already closed (a test checks this).
2. **Market type**: trending up, trending down, ranging or very volatile (1h ADX + EMAs, ATR percentile).
   In "very volatile" the system stands aside.
3. **10 strategies vote** (see the *Strategies* tab): multi-timeframe trend pullback, break of structure +
   order block, fair value gap, liquidity sweep, key levels / round numbers, Asian-range session breakout,
   volatility squeeze, Fibonacci golden zone, mean reversion, RSI divergence. A vote stays alive for 1 hour.
4. **Weighting**: each strategy counts more in the market type where it works best; counter-trend votes count half.
5. **News & dollar**: a strong news or dollar/yield bias against the trade cuts the score; support raises it.
6. **Filters**: no new signal within 30 minutes of high-impact USD news, on Sunday open, late Friday, or at the
   daily rollover. At least 2 strategies must agree and the score must be ≥ 50.
7. **Trade plan**: entry zone = overlap of the agreeing zones; SL beyond the structure that would prove the
   idea wrong (+ buffer + spread); TP1 = 1R (or just before a nearby level), TP2 = 2R, TP3 = 3R.
   Plan: close 50% at TP1 and move SL to entry, close 30% at TP2, let 20% run to TP3.

## Backtest from the command line

```bash
python -m backend.app.backtest                     # uses DATA_PROVIDER
python -m backend.app.backtest --csv my_xauusd.csv # your own history (time,open,high,low,close in UTC)
python -m backend.app.backtest --min-score 65      # only A and A+ signals
```

Free data only covers about 60 days of 15-minute candles. For serious testing, export several years of
XAUUSD M15 (or M1) history from MT5 or Dukascopy to CSV and use `--csv`.

## Tests

```bash
python -m pytest backend/tests
```

## Project layout

```
backend/app/
  data/providers.py      price data (yfinance, Twelve Data, MT5, CSV, synthetic)
  data/intermarket.py    US Dollar Index + 10Y yield bias
  features.py            indicators on 15m with 1h/4h/daily context (no look-ahead)
  strategies/            the 10 strategies + their weights per market type
  engine.py              regime, voting, filters, entry zone / SL / TP / lot size
  backtest.py            bar-by-bar simulation with spread and partial take-profits
  news/calendar.py       economic calendar (Forex Factory feed)
  news/sentiment.py      headlines + Claude / keyword sentiment -> news bias
  main.py                FastAPI server
frontend/                dashboard (TradingView Lightweight Charts, vendored, Apache-2.0)
```
