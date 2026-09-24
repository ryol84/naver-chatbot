"""Forward-geocode Korean addresses via Nominatim (OSM)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ClowderHospitalFinder/1.0 (embed map; https://github.com/ryol84/naver-chatbot)"


def _short_label(hit: dict[str, Any], fallback: str) -> str:
    addr = hit.get("address") or {}
    parts: list[str] = []

    city_raw = addr.get("city") or addr.get("state")
    if city_raw:
        city = (
            str(city_raw)
            .replace("특별자치시", "")
            .replace("특별시", "")
            .replace("광역시", "")
            .replace("특별자치도", "")
            .strip()
            or str(city_raw)
        )
        parts.append(city)

    for key in ("borough", "county", "city_district", "municipality"):
        val = addr.get(key)
        if val and str(val) not in parts:
            parts.append(str(val))
            break

    for key in ("suburb", "neighbourhood", "quarter", "village", "town"):
        val = addr.get(key)
        if val and str(val) not in parts:
            parts.append(str(val))
            break

    if parts:
        return " ".join(parts[:3])
    name = hit.get("name") or hit.get("display_name") or fallback
    return str(name).split(",")[0].strip()


def geocode_kr(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` KR matches: lat, lng, label, display_name."""
    q = (query or "").strip()
    if len(q) < 2:
        return []

    params = urllib.parse.urlencode(
        {
            "q": q,
            "format": "json",
            "limit": str(max(1, min(limit, 8))),
            "countrycodes": "kr",
            "addressdetails": "1",
        }
    )
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ko"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return []

    out: list[dict[str, Any]] = []
    for hit in raw or []:
        try:
            lat = float(hit["lat"])
            lng = float(hit["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        display = str(hit.get("display_name") or q)
        out.append(
            {
                "lat": lat,
                "lng": lng,
                "label": _short_label(hit, q),
                "display_name": display,
            }
        )
    return out
