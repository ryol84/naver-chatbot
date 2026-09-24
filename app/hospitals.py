"""Companion hospital data load + nearby / map search."""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hospitals" / "agent-pack" / "companion-hospitals.jsonl"
SITE_SLIM_PATH = ROOT / "data" / "hospitals" / "site-hospitals-slim.json"

CARE_RANK = {
    "university": 5,
    "secondary": 4,
    "primary": 3,
    "rehab_specialty": 2,
    "neighborhood": 1,
}

CARE_LABEL = {
    "university": "대학병원",
    "secondary": "2차",
    "primary": "1차",
    "neighborhood": "일반",
    "rehab_specialty": "재활",
}

# Department tags that imply imaging / equipment
EQUIP_FROM_DEPT = [
    (re.compile(r"CT|영상\(CT", re.I), "CT"),
    (re.compile(r"MRI|영상\(CT/MRI\)|영상\(MRI", re.I), "MRI"),
    (re.compile(r"초음파", re.I), "초음파"),
    (re.compile(r"내시경", re.I), "내시경"),
    (re.compile(r"복강경", re.I), "복강경"),
    (re.compile(r"방사선|X-?ray|엑스레이", re.I), "X-ray"),
]

# Rough sido bounding boxes to drop rows whose lat/lng disagree with address sido.
# (Some companion rows have Busan-area coords but Gangwon/Jeju/Chungnam addresses.)
_SIDO_BBOX: dict[str, tuple[float, float, float, float]] = {
    # lat_min, lat_max, lng_min, lng_max
    "서울": (37.40, 37.75, 126.75, 127.20),
    "서울특별시": (37.40, 37.75, 126.75, 127.20),
    "부산": (34.85, 35.40, 128.75, 129.35),
    "부산광역시": (34.85, 35.40, 128.75, 129.35),
    "대구": (35.70, 36.05, 128.40, 128.80),
    "대구광역시": (35.70, 36.05, 128.40, 128.80),
    "인천": (37.25, 37.85, 126.30, 126.90),
    "인천광역시": (37.25, 37.85, 126.30, 126.90),
    "광주": (35.05, 35.30, 126.65, 127.05),
    "광주광역시": (35.05, 35.30, 126.65, 127.05),
    "대전": (36.20, 36.50, 127.25, 127.55),
    "대전광역시": (36.20, 36.50, 127.25, 127.55),
    "울산": (35.40, 35.75, 129.05, 129.50),
    "울산광역시": (35.40, 35.75, 129.05, 129.50),
    "세종": (36.40, 36.65, 127.15, 127.40),
    "세종특별자치시": (36.40, 36.65, 127.15, 127.40),
    "경기": (36.85, 38.30, 126.35, 127.90),
    "경기도": (36.85, 38.30, 126.35, 127.90),
    "강원": (37.00, 38.65, 127.05, 129.40),
    "강원도": (37.00, 38.65, 127.05, 129.40),
    "강원특별자치도": (37.00, 38.65, 127.05, 129.40),
    "충북": (36.00, 37.25, 127.20, 128.70),
    "충청북도": (36.00, 37.25, 127.20, 128.70),
    "충남": (35.95, 37.10, 125.95, 127.65),
    "충청남도": (35.95, 37.10, 125.95, 127.65),
    "전북": (35.30, 36.20, 126.35, 127.80),
    "전라북도": (35.30, 36.20, 126.35, 127.80),
    "전북특별자치도": (35.30, 36.20, 126.35, 127.80),
    "전남": (34.20, 35.50, 125.95, 127.85),
    "전라남도": (34.20, 35.50, 125.95, 127.85),
    "경북": (35.55, 37.10, 128.00, 129.65),
    "경상북도": (35.55, 37.10, 128.00, 129.65),
    "경남": (34.50, 35.90, 127.55, 129.30),
    "경상남도": (34.50, 35.90, 127.55, 129.30),
    "제주": (33.10, 33.60, 126.10, 127.00),
    "제주특별자치도": (33.10, 33.60, 126.10, 127.00),
}


def _coords_match_sido(sido: str | None, lat: float, lng: float) -> bool:
    """False when address sido and coordinates clearly disagree."""
    if not sido:
        return True
    key = sido.strip()
    box = _SIDO_BBOX.get(key)
    if box is None:
        for name, b in _SIDO_BBOX.items():
            if key.startswith(name[:2]):
                box = b
                break
    if box is None:
        return True
    lat_min, lat_max, lng_min, lng_max = box
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _equipment_from_departments(departments: list[str] | None) -> list[str]:
    blob = "|".join(departments or [])
    out: list[str] = []
    for pat, label in EQUIP_FROM_DEPT:
        if pat.search(blob) and label not in out:
            out.append(label)
    return out


def _is_emergency(departments: list[str] | None, hours_24h: str | None) -> bool:
    deps = departments or []
    if "응급" in deps:
        return True
    if hours_24h == "yes" and any("외과" in d for d in deps):
        return True
    return False


def _is_emergency_surgery(departments: list[str] | None) -> bool:
    deps = departments or []
    has_er = "응급" in deps
    has_surg = any("외과" in d for d in deps)
    return has_er and has_surg


@lru_cache(maxsize=1)
def _site_equipment_index() -> dict[tuple[float, float], dict[str, Any]]:
    """Join verified site-slim equipment onto companion rows by rounded lat/lng."""
    idx: dict[tuple[float, float], dict[str, Any]] = {}
    if not SITE_SLIM_PATH.is_file():
        return idx
    payload = json.loads(SITE_SLIM_PATH.read_text(encoding="utf-8"))
    for h in payload.get("hospitals") or []:
        if h.get("lat") is None or h.get("lng") is None:
            continue
        key = (round(float(h["lat"]), 4), round(float(h["lng"]), 4))
        idx[key] = {
            "equipment": list(h.get("equipment") or []),
            "services": list(h.get("services") or []),
            "emergency_site": h.get("emergency"),
            "site_id": h.get("id"),
        }
    return idx


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    deps = list(row.get("departments") or [])
    equip = _equipment_from_departments(deps)
    site = _site_equipment_index().get(
        (round(float(row["lat"]), 4), round(float(row["lng"]), 4))
    )
    if site and site.get("equipment"):
        # Prefer verified model names; keep inferred tags that aren't covered
        merged = list(site["equipment"])
        for e in equip:
            if e not in " ".join(merged):
                merged.append(e)
        equip = merged

    hours_24h = row.get("hours_24h")
    emergency = _is_emergency(deps, hours_24h)
    if site and site.get("emergency_site") == "yes":
        emergency = True

    out = dict(row)
    out["equipment"] = equip
    out["is_24h"] = hours_24h == "yes"
    out["is_emergency"] = emergency
    out["is_emergency_surgery"] = _is_emergency_surgery(deps)
    out["care_level_short"] = CARE_LABEL.get(row.get("care_level") or "", row.get("care_level_ko") or "")
    out["priority"] = int(out["is_24h"]) * 2 + int(out["is_emergency_surgery"] or out["is_emergency"])
    return out


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
            lat, lng = float(row["lat"]), float(row["lng"])
            # Drop swapped/wrong geocodes (e.g. Busan coords + Gangwon address)
            if not _coords_match_sido(row.get("sido"), lat, lng):
                continue
            rows.append(_enrich(row))
    return tuple(rows)


def _dept_match(departments: list[str] | None, keywords: list[str]) -> bool:
    if not keywords:
        return True
    blob = "|".join(departments or []).lower()
    return any(k.lower() in blob for k in keywords)


def search_nearby(
    *,
    lat: float,
    lng: float,
    radius_km: float = 8.0,
    limit: int = 40,
    need_24h: bool = False,
    need_emergency: bool = False,
    care_levels: list[str] | None = None,
    department_keywords: list[str] | None = None,
    prefer_emergency_dept: bool = False,
    hard_department_filter: bool = False,
) -> list[dict[str, Any]]:
    """Nearby hospitals. 24h + emergency surgery float to the top."""
    dept_kw = department_keywords or []
    care_allow = set(care_levels) if care_levels else None

    scored: list[tuple[int, float, float, dict[str, Any], float]] = []
    for h in load_hospitals():
        if need_24h and not h.get("is_24h"):
            continue
        if need_emergency and not (h.get("is_emergency") or h.get("is_emergency_surgery")):
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
        priority = int(h.get("priority") or 0)  # 24h/응급 상단
        emergency_boost = 1.5 if h.get("is_emergency") else 0.0
        if prefer_emergency_dept and h.get("is_emergency"):
            emergency_boost += 1.0
        h24_boost = 1.5 if h.get("is_24h") else 0.0
        surg_boost = 1.0 if h.get("is_emergency_surgery") else 0.0
        dept_boost = 2.0 if dept_hit else 0.0
        fit = care + emergency_boost + h24_boost + surg_boost + dept_boost - dist * 0.12

        # Sort key: priority desc, fit desc, closer
        scored.append((priority, fit, -dist, h, dist))

    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)

    out: list[dict[str, Any]] = []
    for priority, fit, _neg, h, dist in scored[:limit]:
        out.append(
            {
                "id": h.get("id"),
                "name": h.get("name"),
                "care_level": h.get("care_level"),
                "care_level_ko": h.get("care_level_ko"),
                "care_level_short": h.get("care_level_short"),
                "address": h.get("address"),
                "sido": h.get("sido"),
                "sigungu": h.get("sigungu"),
                "lat": h.get("lat"),
                "lng": h.get("lng"),
                "phone": h.get("phone"),
                "homepage": h.get("homepage"),
                "hours_24h": h.get("hours_24h"),
                "is_24h": h.get("is_24h"),
                "is_emergency": h.get("is_emergency"),
                "is_emergency_surgery": h.get("is_emergency_surgery"),
                "weekday_hours": h.get("weekday_hours"),
                "weekend_hours": h.get("weekend_hours"),
                "departments": h.get("departments") or [],
                "equipment": h.get("equipment") or [],
                "distance_km": round(dist, 2),
                "daum_map_url": h.get("daum_map_url"),
                "place_search_url": h.get("place_search_url"),
                "fit_score": round(fit, 3),
                "priority": priority,
                "department_match": bool(dept_kw and dept_hit),
            }
        )
    return out


@lru_cache(maxsize=1)
def _raw_coord_count() -> int:
    n = 0
    with DATA_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("lat") is not None and row.get("lng") is not None:
                n += 1
    return n


def stats() -> dict[str, Any]:
    rows = load_hospitals()
    by_care: dict[str, int] = {}
    h24 = er = er_surg = with_equip = 0
    for h in rows:
        by_care[h.get("care_level") or "unknown"] = by_care.get(h.get("care_level") or "unknown", 0) + 1
        if h.get("is_24h"):
            h24 += 1
        if h.get("is_emergency"):
            er += 1
        if h.get("is_emergency_surgery"):
            er_surg += 1
        if h.get("equipment"):
            with_equip += 1
    raw = _raw_coord_count()
    return {
        "total_with_coords": len(rows),
        "excluded_coord_mismatch": max(0, raw - len(rows)),
        "by_care_level": by_care,
        "hours_24h_yes": h24,
        "emergency": er,
        "emergency_surgery": er_surg,
        "with_equipment_signal": with_equip,
    }
