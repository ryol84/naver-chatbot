from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.hospitals import search_nearby, stats
from app.triage import CITY_PRESETS, SEVERITIES, SYMPTOMS, resolve_filters

app = FastAPI(title="바로벳 — 근처 동물병원 찾기")

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
        "stats": stats(),
    }


@app.get("/api/hospitals/nearby")
async def hospitals_nearby(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude"),
    symptom: str | None = Query(None, description="Symptom id from /api/triage/options"),
    severity: str | None = Query(None, description="Severity id"),
    need_24h: bool = Query(False, description="Require hours_24h=yes"),
    radius_km: float | None = Query(None, ge=0.5, le=50),
    limit: int = Query(20, ge=1, le=50),
):
    filters = resolve_filters(symptom_id=symptom, severity_id=severity, need_24h=need_24h)
    use_radius = radius_km if radius_km is not None else filters["radius_km"]

    results = search_nearby(
        lat=lat,
        lng=lng,
        radius_km=use_radius,
        limit=limit,
        need_24h=filters["need_24h"],
        min_care_levels=filters["care_levels"],
        department_keywords=filters["department_keywords"],
        prefer_emergency_dept=filters["prefer_emergency_dept"],
    )

    relaxed = False
    if not results:
        relaxed = True
        results = search_nearby(
            lat=lat,
            lng=lng,
            radius_km=min(use_radius * 1.8, 30),
            limit=limit,
            need_24h=filters["need_24h"],
            min_care_levels=None,
            department_keywords=filters["department_keywords"],
            prefer_emergency_dept=filters["prefer_emergency_dept"],
        )

    return {
        "count": len(results),
        "filters": {
            "symptom": symptom,
            "severity": severity,
            "need_24h": filters["need_24h"],
            "prefer_24h": filters["prefer_24h"],
            "radius_km": use_radius,
            "care_levels": filters["care_levels"],
            "department_keywords": filters["department_keywords"],
            "relaxed": relaxed,
        },
        "hospitals": results,
    }


@app.post("/naver-callback")
async def naver_callback(request: Request):
    data = await request.json()
    message = data.get("content", "")

    if openai is None or not os.getenv("OPENAI_API_KEY"):
        answer = (
            "바로벳 근처 병원 찾기는 웹에서 이용할 수 있어요. "
            "증상·중증도·24시 여부를 고르면 주변 병원을 바로 보여줍니다."
        )
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
