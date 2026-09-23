from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.hospitals import CARE_LABEL, search_nearby, stats
from app.triage import CITY_PRESETS, SEVERITIES, SYMPTOMS, resolve_filters

app = FastAPI(title="Clowder hospital map embed")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

try:
    import openai  # type: ignore

    openai.api_key = os.getenv("OPENAI_API_KEY")
except Exception:  # pragma: no cover
    openai = None  # type: ignore


@app.get("/")
async def finder_home():
    """Embeddable map panel for Clowder (no marketing hero)."""
    return FileResponse(STATIC_DIR / "finder.html")


@app.get("/benchmark")
async def benchmark_page():
    return FileResponse(STATIC_DIR / "benchmark.html")


@app.get("/api/health")
async def health():
    return {"ok": True, **stats()}


@app.get("/api/triage/options")
async def triage_options():
    return {
        "symptoms": SYMPTOMS,
        "severities": SEVERITIES,
        "cities": CITY_PRESETS,
        "care_levels": [
            {"id": "university", "label": CARE_LABEL["university"]},
            {"id": "secondary", "label": CARE_LABEL["secondary"]},
            {"id": "primary", "label": CARE_LABEL["primary"]},
            {"id": "neighborhood", "label": CARE_LABEL["neighborhood"]},
        ],
        "stats": stats(),
    }


@app.get("/api/hospitals/nearby")
async def hospitals_nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    symptom: str | None = Query(None),
    severity: str | None = Query(None),
    need_24h: bool = Query(False),
    need_emergency: bool = Query(False),
    care_levels: str | None = Query(
        None,
        description="Comma-separated: university,secondary,primary,neighborhood",
    ),
    radius_km: float | None = Query(None, ge=0.5, le=50),
    limit: int = Query(40, ge=1, le=80),
):
    filters = resolve_filters(symptom_id=symptom, severity_id=severity, need_24h=need_24h)
    use_radius = radius_km if radius_km is not None else filters["radius_km"]

    level_list: list[str] | None = None
    if care_levels:
        level_list = [x.strip() for x in care_levels.split(",") if x.strip()]
    elif severity:
        level_list = filters["care_levels"]

    results = search_nearby(
        lat=lat,
        lng=lng,
        radius_km=use_radius,
        limit=limit,
        need_24h=filters["need_24h"] or need_24h,
        need_emergency=need_emergency,
        care_levels=level_list,
        department_keywords=filters["department_keywords"] if symptom else [],
        prefer_emergency_dept=filters["prefer_emergency_dept"] or need_emergency,
    )

    relaxed = False
    if not results:
        relaxed = True
        results = search_nearby(
            lat=lat,
            lng=lng,
            radius_km=min(use_radius * 1.8, 30),
            limit=limit,
            need_24h=need_24h,
            need_emergency=False,
            care_levels=None,
            department_keywords=[],
            prefer_emergency_dept=need_emergency,
        )

    featured = [h for h in results if h.get("is_24h") or h.get("is_emergency_surgery") or h.get("is_emergency")]
    rest = [h for h in results if h not in featured]

    return {
        "count": len(results),
        "filters": {
            "symptom": symptom,
            "severity": severity,
            "need_24h": need_24h or filters["need_24h"],
            "need_emergency": need_emergency,
            "radius_km": use_radius,
            "care_levels": level_list,
            "department_keywords": filters["department_keywords"] if symptom else [],
            "relaxed": relaxed,
        },
        "featured": featured,
        "hospitals": featured + rest,
    }


@app.post("/naver-callback")
async def naver_callback(request: Request):
    data = await request.json()
    message = data.get("content", "")

    if openai is None or not os.getenv("OPENAI_API_KEY"):
        answer = "클라우더 병원 지도에서 위치·등급·24시·응급으로 근처 병원을 확인할 수 있어요."
    else:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message}],
        )
        answer = response.choices[0].message.content.strip()

    return JSONResponse(
        {
            "version": "2.0",
            "template": {"outputs": [{"simpleText": {"text": answer}}]},
        }
    )
