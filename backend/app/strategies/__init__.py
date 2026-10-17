"""Registry of all strategies and how much each is trusted per market regime."""
from .base import BUY, SELL, Ctx, Strategy, Vote
from .price_action import fair_value_gap, fib_confluence, key_levels, liquidity_sweep, structure_order_block
from .reversion import mean_reversion, rsi_divergence
from .trend import session_breakout, squeeze_breakout, trend_pullback

# weights by regime: trend (trend_up / trend_down) / range / volatile
STRATEGIES: list[Strategy] = [
    Strategy("trend_pullback", "MTF trend pullback",
             "4h + 1h EMA trend agree; enter on 15m pullback to EMA20/50",
             trend_pullback, {"trend": 1.2, "range": 0.4, "volatile": 0.5}),
    Strategy("structure_ob", "Break of structure + order block",
             "Close beyond last swing, then first retest of the order block",
             structure_order_block, {"trend": 1.1, "range": 0.7, "volatile": 0.6}),
    Strategy("fvg", "Fair value gap",
             "First return into an unfilled 3-candle imbalance",
             fair_value_gap, {"trend": 1.0, "range": 0.7, "volatile": 0.5}),
    Strategy("liquidity_sweep", "Liquidity sweep",
             "Stop hunt beyond a swing / previous-day / Asian level, then close back inside",
             liquidity_sweep, {"trend": 0.8, "range": 1.2, "volatile": 0.6}),
    Strategy("key_levels", "Key levels",
             "Rejection at $25 round numbers or previous-day high/low/close",
             key_levels, {"trend": 0.9, "range": 1.1, "volatile": 0.5}),
    Strategy("session_breakout", "Session breakout",
             "London / NY break of the Asian range, buy/sell the retest",
             session_breakout, {"trend": 1.0, "range": 0.8, "volatile": 0.5}),
    Strategy("squeeze", "Volatility squeeze",
             "Bollinger inside Keltner, then expansion with momentum",
             squeeze_breakout, {"trend": 0.9, "range": 1.0, "volatile": 0.4}),
    Strategy("fib", "Fibonacci golden zone",
             "Trend pullback into the 50-70.5% retracement",
             fib_confluence, {"trend": 1.1, "range": 0.5, "volatile": 0.5}),
    Strategy("mean_reversion", "Mean reversion",
             "RSI extreme outside Bollinger Band, back inside (ranges only)",
             mean_reversion, {"trend": 0.3, "range": 1.2, "volatile": 0.3}),
    Strategy("divergence", "RSI divergence",
             "Lower low / higher high not confirmed by RSI",
             rsi_divergence, {"trend": 0.5, "range": 1.1, "volatile": 0.4}),
]

BY_NAME = {s.name: s for s in STRATEGIES}

__all__ = ["BUY", "SELL", "Ctx", "Strategy", "Vote", "STRATEGIES", "BY_NAME"]
