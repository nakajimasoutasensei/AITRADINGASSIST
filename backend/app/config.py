"""Settings loaded from environment variables / .env file."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_provider: str = os.getenv("DATA_PROVIDER", "yfinance").strip().lower()
    twelvedata_api_key: str = os.getenv("TWELVEDATA_API_KEY", "").strip()
    mt5_symbol: str = os.getenv("MT5_SYMBOL", "XAUUSD").strip()
    mt5_utc_offset: float = _float("MT5_UTC_OFFSET", 0.0)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5-5").strip()
    account_balance: float = _float("ACCOUNT_BALANCE", 1000.0)
    risk_percent: float = _float("RISK_PERCENT", 1.0)
    spread: float = _float("SPREAD", 0.30)
    # XAUUSD: 1 standard lot = 100 oz, so $1 move = $100 per lot
    contract_size: float = 100.0


settings = Settings()
