# --- utils_time_dual.py ---
from __future__ import annotations
from datetime import datetime, timedelta, timezone, date
try:
    from zoneinfo import ZoneInfo  # Py3.9+
except Exception:  # very old Pythons
    ZoneInfo = None  # type: ignore

from config_dual import RIYADH_TZ

def _tz():
    """Return a tzinfo for Riyadh. Fallback to UTC+03 if the IANA zone isn’t available."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(RIYADH_TZ)
        except Exception:
            pass
    return timezone(timedelta(hours=3), name="Asia/Riyadh")

def now_riyadh() -> datetime:
    """Aware datetime in Riyadh tz."""
    return datetime.now(_tz())

def stamp_riyadh() -> tuple[str, str]:
    """
    Returns (date_str, time_str) in Riyadh.
    date: YYYY-MM-DD
    time: HH:MM:SS
    """
    dt = now_riyadh()
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")

def parse_week_id(week_id: str) -> tuple[int, int]:
    """
    Parse 'Week_YYYY_WW' -> (year, iso_week).
    Example: 'Week_2025_46' -> (2025, 46)
    """
    parts = week_id.split("_")
    if len(parts) != 3 or parts[0] != "Week":
        raise ValueError(f"Invalid week_id format: {week_id}")
    return int(parts[1]), int(parts[2])

def week_monday(week_id: str) -> date:
    """Return the Monday date of the ISO week represented by week_id."""
    y, w = parse_week_id(week_id)
    return date.fromisocalendar(y, w, 1)  # Monday

def next_week_id(week_id: str) -> str:
    """
    Advance by 7 days from the Monday of this week and return the new 'Week_YYYY_WW'.
    Keeps the same non-zero-padded style as your Firestore paths (e.g., Week_2025_47).
    """
    mon = week_monday(week_id)
    nxt = mon + timedelta(days=7)
    iso = nxt.isocalendar()  # (year, week, weekday)
    return f"Week_{iso.year}_{iso.week}"

def week_id_sequence(start_week_id: str, total_weeks: int, include_start: bool = True) -> list[str]:
    """
    Build a list of Week IDs.
      - If include_start=True and total_weeks=1 -> [start_week_id]
      - Otherwise advance with next_week_id until length matches total_weeks.
    """
    if total_weeks <= 0:
        return []
    seq = []
    cur = start_week_id
    if include_start:
        seq.append(cur)
    for _ in range(total_weeks - (1 if include_start else 0)):
        cur = next_week_id(cur)
        seq.append(cur)
    return seq

__all__ = [
    "now_riyadh",
    "stamp_riyadh",
    "parse_week_id",
    "week_monday",
    "next_week_id",
    "week_id_sequence",
]
