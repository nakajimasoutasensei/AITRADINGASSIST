"""Common types for strategies.

A strategy looks at bar i (and only bars before it) and may return a Vote:
direction, an entry zone, the price that proves the idea wrong, and a confidence.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np
import pandas as pd

BUY, SELL = 1, -1


@dataclass
class Vote:
    strategy: str
    direction: int  # +1 buy, -1 sell
    zone_low: float
    zone_high: float
    invalidation: float  # stop-loss reference: below it (buy) / above it (sell) the idea is wrong
    confidence: float  # 0..1
    reason: str
    bar: int = -1  # bar position where the vote was created

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = "BUY" if self.direction == BUY else "SELL"
        return d


class Ctx:
    """Fast column access: ctx.c('close', i) or ctx['close'][i]."""

    def __init__(self, f: pd.DataFrame):
        self.f = f
        self.index = f.index
        self.n = len(f)
        self._cols = {c: f[c].to_numpy(dtype=float) for c in f.columns if np.issubdtype(f[c].dtype, np.number)}

    def __getitem__(self, col: str) -> np.ndarray:
        return self._cols[col]

    def v(self, col: str, i: int) -> float:
        return float(self._cols[col][i])


def ok(*xs: float) -> bool:
    return all(x is not None and not math.isnan(x) for x in xs)


@dataclass(frozen=True)
class Strategy:
    name: str
    label: str
    description: str
    fn: Callable[[Ctx, int], "Vote | None"]
    # how much to trust this strategy in each market regime
    weights: dict

    def evaluate(self, ctx: Ctx, i: int) -> Vote | None:
        vote = self.fn(ctx, i)
        if vote is None:
            return None
        lo, hi = sorted((vote.zone_low, vote.zone_high))
        vote.zone_low, vote.zone_high = lo, hi
        vote.strategy = self.name
        vote.bar = i
        vote.confidence = float(min(max(vote.confidence, 0.0), 1.0))
        return vote
