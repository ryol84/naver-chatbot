"""Companion hospital data load + nearby search."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "hospitals"
    / "agent-pack"
    / "companion-hospitals.jsonl"
)

CARE_RANK = {
    "university": 5,
    "secondary": 4,
    "primary": 3,
    "rehab_specialty": 2,
    "neighborhood": 1,
}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_hospitals() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    with DATA_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("lat") is None or row.get("lng") is None:
                continue
            rows.append(row)
    return tuple(rows)


def _dept_match(departments: list[str] | None, keywords: list[str]) -> bool:
    if not keywords:
        return True
    deps = departments or []
    blob = "|".join(deps).lower()
    return any(k.lower() in blob for k in keywords)


def search_nearby(
    *,
    lat: float,
    lng: float,
    radius_km: float = 8.0,
    limit: int = 20,
    need_24h: bool = False,
    min_care_levels: list[str] | None = None,
    department_keywords: list[str] | None = None,
    prefer_emergency_dept: bool = False,
    hard_department_filter: bool = False,
) -> list[dict[str, Any]]:
    """Return hospitals near lat/lng matching triage filters, sorted by fit then distance.

    Department keywords boost ranking by default (Korean neighborhood clinics often
    only list 일반진료). Set hard_department_filter=True to require a keyword hit.
    """
    dept_kw = department_keywords or []
    care_allow = set(min_care_levels) if min_care_levels else None

    scored: list[tuple[float, float, dict[str, Any], float]] = []
    for h in load_hospitals():
        if need_24h and h.get("hours_24h") != "yes":
            continue
        if care_allow is not None and h.get("care_level") not in care_allow:
            continue

        dept_hit = _dept_match(h.get("departments"), dept_kw) if dept_kw else False
        if hard_department_filter and dept_kw and not dept_hit:
            continue

        dist = haversine_km(lat, lng, float(h["lat"]), float(h["lng"]))
        if dist > radius_km:
            continue

        care = CARE_RANK.get(h.get("care_level") or "", 0)
        emergency_boost = 1.5 if "응급" in (h.get("departments") or []) else 0.0
        if prefer_emergency_dept and emergency_boost:
            emergency_boost += 1.0
        h24_boost = 1.0 if h.get("hours_24h") == "yes" else 0.0
        dept_boost = 2.2 if dept_hit else 0.0
        # Higher fit first; closer wins ties
        fit = care + emergency_boost + h24_boost + dept_boost - dist * 0.15
        scored.append((fit, -dist, h, dist))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

    out: list[dict[str, Any]] = []
    for fit, _neg, h, dist in scored[:limit]:
        out.append(
            {
                "id": h.get("id"),
                "name": h.get("name"),
                "care_level": h.get("care_level"),
                "care_level_ko": h.get("care_level_ko"),
                "address": h.get("address"),
                "sido": h.get("sido"),
                "sigungu": h.get("sigungu"),
                "lat": h.get("lat"),
                "lng": h.get("lng"),
                "phone": h.get("phone"),
                "homepage": h.get("homepage"),
                "hours_24h": h.get("hours_24h"),
                "weekday_hours": h.get("weekday_hours"),
                "weekend_hours": h.get("weekend_hours"),
                "departments": h.get("departments") or [],
                "distance_km": round(dist, 2),
                "daum_map_url": h.get("daum_map_url"),
                "place_search_url": h.get("place_search_url"),
                "fit_score": round(fit, 3),
                "department_match": bool(
                    dept_kw and _dept_match(h.get("departments"), dept_kw)
                ),
            }
        )
    return out


def stats() -> dict[str, Any]:
    rows = load_hospitals()
    by_care: dict[str, int] = {}
    h24 = 0
    for h in rows:
        by_care[h.get("care_level") or "unknown"] = by_care.get(h.get("care_level") or "unknown", 0) + 1
        if h.get("hours_24h") == "yes":
            h24 += 1
    return {"total_with_coords": len(rows), "by_care_level": by_care, "hours_24h_yes": h24}
