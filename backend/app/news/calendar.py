"""Economic calendar (Forex Factory weekly feed). Used to pause trading around big USD news."""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests

log = logging.getLogger(__name__)
FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_cache: tuple[float, list[dict]] | None = None


def get_events(ttl: float = 3600) -> list[dict]:
    """All USD events this week with impact Medium/High. Times in UTC ISO format."""
    global _cache
    if _cache and time.time() - _cache[0] < ttl:
        return _cache[1]
    try:
        r = requests.get(FEED, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        raw = r.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("calendar fetch failed: %s", e)
        return _cache[1] if _cache else []
    events = []
    for ev in raw:
        if ev.get("country") != "USD" or ev.get("impact") not in ("High", "Medium"):
            continue
        try:
            t = pd.Timestamp(ev["date"]).tz_convert("UTC")
        except (KeyError, ValueError, TypeError):
            continue
        events.append({
            "time": t.isoformat(),
            "title": ev.get("title", ""),
            "impact": ev.get("impact"),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
        })
    events.sort(key=lambda e: e["time"])
    _cache = (time.time(), events)
    return events


def high_impact(events: list[dict]) -> list[dict]:
    return [e for e in events if e["impact"] == "High"]
