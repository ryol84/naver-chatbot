"""Normalize companion hospital opening hours into a clean display structure."""
from __future__ import annotations

import re
from typing import Any

_TIME_RANGE = re.compile(
    r"(\d{1,2}:\d{2})\s*[–\-〜~]\s*(\d{1,2}:\d{2}|24:00)"
)
_SAT = re.compile(r"토\s*([^·\n]+)")
_SUN = re.compile(r"일\s*([^·\n]+)")


def _clean_span(text: str | None) -> str | None:
    if not text:
        return None
    s = str(text).strip()
    s = s.replace("〜", "–").replace("~", "–").replace("-", "–")
    s = re.sub(r"\s+", " ", s)
    if not s or s in {"None", "null", "-"}:
        return None
    # Normalize 00:00–24:00 variants
    if re.fullmatch(r"00:00\s*–\s*(24:00|00:00)", s) or s in {"24시간", "24시", "연중무휴"}:
        return "24시간"
    return s


def _parse_day_token(token: str | None) -> str | None:
    if not token:
        return None
    t = token.strip()
    t = t.replace("〜", "–").replace("~", "–").replace("-", "–")
    t = re.sub(r"\s+", " ", t).strip(" ·")
    if not t:
        return None
    if "휴무" in t or t in {"휴진", "폐쇄"}:
        return "휴무"
    if "24" in t and ("시간" in t or "시" in t or "00:00" in t):
        return "24시간"
    m = _TIME_RANGE.search(t)
    if m:
        return f"{m.group(1)}–{m.group(2)}"
    return t


def _split_weekend(weekend_hours: str | None) -> tuple[str | None, str | None]:
    if not weekend_hours:
        return None, None
    raw = weekend_hours.strip()
    sat = sun = None
    ms = _SAT.search(raw)
    mu = _SUN.search(raw)
    if ms:
        sat = _parse_day_token(ms.group(1))
    if mu:
        sun = _parse_day_token(mu.group(1))
    # Fallback: single range applies to both if no 토/일 labels
    if sat is None and sun is None:
        span = _clean_span(raw)
        if span:
            return span, span
    return sat, sun


def format_hours(
    *,
    hours_24h: str | None = None,
    weekday_hours: str | None = None,
    weekend_hours: str | None = None,
) -> dict[str, Any]:
    """Return structured hours for UI cards.

    {
      is_24h: bool,
      weekday: "10:00–19:00" | "24시간" | None,
      saturday: "10:00–17:00" | "휴무" | None,
      sunday: "휴무" | None,
      lines: ["평일 10:00–19:00", "토 10:00–17:00", "일 휴무"],
      summary: "평일 10:00–19:00 · 토 10:00–17:00 · 일 휴무",
      unknown: bool,
    }
    """
    is_24h = hours_24h == "yes"
    weekday = _clean_span(weekday_hours)
    saturday, sunday = _split_weekend(weekend_hours)

    if is_24h or weekday == "24시간":
        return {
            "is_24h": True,
            "weekday": "24시간",
            "saturday": "24시간",
            "sunday": "24시간",
            "lines": ["24시간 영업"],
            "summary": "24시간 영업",
            "unknown": False,
        }

    # If weekday looks like 24h range but flag isn't yes, still show as span
    if weekday == "24시간":
        weekday = "00:00–24:00"

    lines: list[str] = []
    if weekday:
        lines.append(f"평일 {weekday}")
    if saturday:
        lines.append(f"토 {saturday}")
    if sunday:
        lines.append(f"일 {sunday}")

    unknown = not lines
    if unknown:
        lines = ["영업시간 정보 없음"]

    return {
        "is_24h": False,
        "weekday": weekday,
        "saturday": saturday,
        "sunday": sunday,
        "lines": lines,
        "summary": " · ".join(lines),
        "unknown": unknown,
    }
