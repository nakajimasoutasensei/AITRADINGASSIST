"""Machine-learning "meta-model": learns from history which strategy combinations actually reach TP1.

How it works:
  1. Run the engine over history with relaxed rules to collect many candidate trades.
  2. Simulate each candidate (same rules as the backtest) -> label 1 if TP1 was hit before the stop.
  3. Train a gradient-boosting classifier on the candidate's features (strategy votes, regime,
     session, distance to key levels, momentum, ...).
  4. Honest check: the model is trained on the older 70% and tested on the newest 30% it never saw.
  5. Live, a signal is only shown when the model's probability is above the chosen threshold.

Train:   python -m backend.app.ml --csv xauusd_m15.csv      (several years of data recommended)
         python -m backend.app.ml                           (uses DATA_PROVIDER, ~60 days: weak)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from .backtest import WARMUP, compute_votes, simulate
from .config import ROOT
from .engine import EngineConfig, decide
from .features import build_features
from .strategies import Ctx

log = logging.getLogger(__name__)
MODEL_PATH = ROOT / "models" / "meta_model.joblib"
# looser than the normal engine so the model sees (and can learn to filter) many more setups
CANDIDATE_RULES = {"min_agree": 1, "min_score": 25.0}


@dataclass
class MetaModel:
    model: HistGradientBoostingClassifier
    feature_names: list
    threshold: float
    min_agree: int
    min_score: float
    report: dict = field(default_factory=dict)

    def probability(self, feats: dict) -> float:
        row = np.array([[feats.get(n, np.nan) for n in self.feature_names]], dtype=float)
        return float(self.model.predict_proba(row)[0, 1])


# ------------------------------------------------------------------ dataset


def make_dataset(df: pd.DataFrame) -> pd.DataFrame:
    cfg = EngineConfig(**CANDIDATE_RULES)
    x = Ctx(build_features(df))
    history = compute_votes(x, WARMUP)
    rows = []
    for i in sorted(history):
        if i >= x.n - 2:
            continue
        a = decide(x, i, history, cfg)
        sig = a["signal"]
        if sig is None:
            continue
        t, _ = simulate(x, i, sig, cfg.spread)
        if not t.fill_time:  # only learn from trades that actually got filled
            continue
        rows.append({**a["ml_features"], "time": x.index[i], "y": int(t.tp1_hit), "r": t.result_r})
    return pd.DataFrame(rows)


def _new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=40, l2_regularization=1.0, random_state=0
    )


def _pick_threshold(p: np.ndarray, r: np.ndarray, min_trades: int) -> float:
    """Threshold that gives the best total R on validation data, keeping enough trades."""
    best_t, best_score = 0.5, -math.inf
    for t in np.arange(0.40, 0.81, 0.025):
        keep = p >= t
        if keep.sum() < min_trades:
            continue
        score = r[keep].sum()
        if score > best_score:
            best_t, best_score = float(t), score
    return best_t


def _summary(y: np.ndarray, r: np.ndarray) -> dict:
    if len(y) == 0:
        return {"trades": 0}
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": int(len(y)), "win_rate_tp1": round(100 * float(y.mean()), 1),
            "avg_r": round(float(r.mean()), 3), "total_r": round(float(r.sum()), 2),
            "profit_factor": round(float(wins / losses), 2) if losses > 0 else None}


def train(df: pd.DataFrame, path=MODEL_PATH, min_rows: int = 300) -> MetaModel:
    data = make_dataset(df).sort_values("time").reset_index(drop=True)
    if len(data) < min_rows:
        raise ValueError(
            f"Only {len(data)} filled candidate trades in this data (need {min_rows}). "
            "Use more history, e.g. several years of M15 from MT5 exported to CSV.")
    names = [c for c in data.columns if c not in ("time", "y", "r")]
    X, y, r, t = data[names].to_numpy(float), data["y"].to_numpy(), data["r"].to_numpy(float), data["time"]

    # time split: train on the oldest 70%, test on the newest 30%, with a 1-day gap against leakage
    cut = int(len(data) * 0.7)
    test_mask = (t > t.iloc[cut - 1] + pd.Timedelta(days=1)).to_numpy()
    train_idx, test_idx = np.arange(cut), np.where(test_mask)[0]

    # choose the threshold on the last 20% of the training period (validation), never on the test set
    v = int(cut * 0.8)
    m_val = _new_model().fit(X[:v], y[:v])
    threshold = _pick_threshold(m_val.predict_proba(X[v:cut])[:, 1], r[v:cut], min_trades=max(15, (cut - v) // 10))

    m_test = _new_model().fit(X[train_idx], y[train_idx])
    p_test = m_test.predict_proba(X[test_idx])[:, 1]
    keep = p_test >= threshold
    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_from": str(t.iloc[0]), "data_to": str(t.iloc[-1]),
        "candidates": int(len(data)), "features": len(names), "threshold": round(threshold, 3),
        "test_period_from": str(t.iloc[test_idx[0]]) if len(test_idx) else None,
        "test_auc": round(float(roc_auc_score(y[test_idx], p_test)), 3) if len(set(y[test_idx])) > 1 else None,
        "test_all_candidates": _summary(y[test_idx], r[test_idx]),
        "test_model_approved": _summary(y[test_idx][keep], r[test_idx][keep]),
    }

    # final model for live use: trained on all data, same threshold
    final = MetaModel(_new_model().fit(X, y), names, threshold, CANDIDATE_RULES["min_agree"],
                      CANDIDATE_RULES["min_score"], report)
    path.parent.mkdir(parents=True, exist_ok=True)
    # saved as plain data (not the MetaModel class) so it loads no matter how the script was started
    joblib.dump({"model": final.model, "feature_names": names, "threshold": threshold,
                 "min_agree": final.min_agree, "min_score": final.min_score, "report": report}, path)
    _loaded.clear()
    return final


# ------------------------------------------------------------------ loading

_loaded: dict = {}


def load(path=MODEL_PATH) -> MetaModel | None:
    """Loads the trained model if the file exists (reloads automatically after re-training)."""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _loaded.get("mtime") != mtime or _loaded.get("path") != path:
        try:
            _loaded.update(model=MetaModel(**joblib.load(path)), mtime=mtime, path=path)
        except Exception as e:  # corrupted / incompatible file
            log.warning("could not load ML model %s: %s", path, e)
            return None
    return _loaded["model"]


def main() -> None:  # pragma: no cover - CLI
    from .data.providers import get_candles, load_csv

    p = argparse.ArgumentParser(description="Train the ML signal filter")
    p.add_argument("--csv", default=None, help="CSV with time,open,high,low,close[,volume] in UTC")
    p.add_argument("--provider", default=None)
    p.add_argument("--utc-offset", type=float, default=None,
                   help="hours the CSV time is ahead of UTC (MT5 broker time); default MT5_UTC_OFFSET")
    p.add_argument("--min-rows", type=int, default=300)
    a = p.parse_args()
    if a.utc_offset is None:
        from .config import settings

        a.utc_offset = settings.mt5_utc_offset if a.csv else 0.0
    df = load_csv(a.csv, a.utc_offset) if a.csv else get_candles(a.provider)
    print(f"Building candidate trades from {len(df)} candles ({df.index[0]} -> {df.index[-1]}) ...")
    m = train(df, min_rows=a.min_rows)
    print(json.dumps(m.report, indent=2))
    print(f"Saved to {MODEL_PATH}. Restart the server (or just reload the page) to use it.")


if __name__ == "__main__":  # pragma: no cover
    main()
