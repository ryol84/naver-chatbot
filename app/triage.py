"""Symptom / severity triage → hospital filter mapping.

Benchmarked loosely against Vetster teletriage buckets,
VetsOpenNow emergency-first ranking, and Vets Now postcode finder.
"""
from __future__ import annotations

from typing import Any

# Body-region buttons → department keyword hints present in companion DB
SYMPTOMS: list[dict[str, Any]] = [
    {
        "id": "eye",
        "label": "눈·시력",
        "hint": "충혈, 분비물, 눈을 깜빡임",
        "department_keywords": ["안과", "눈"],
    },
    {
        "id": "ear_skin",
        "label": "귀·피부",
        "hint": "가려움, 발진, 귀냄새",
        "department_keywords": ["피부", "피부과", "귀"],
    },
    {
        "id": "dental",
        "label": "이빨·구강",
        "hint": "구취, 잇몸, 씹기 불편",
        "department_keywords": ["치과", "구강"],
    },
    {
        "id": "digest",
        "label": "구토·설사",
        "hint": "소화기, 식욕저하",
        "department_keywords": ["내과", "응급"],
    },
    {
        "id": "breath",
        "label": "호흡·기침",
        "hint": "헐떡임, 코막힘",
        "department_keywords": ["내과", "심장", "응급"],
    },
    {
        "id": "ortho",
        "label": "다리·절뚝",
        "hint": "파행, 슬개골, 외상",
        "department_keywords": ["외과", "슬개골", "정형", "외과(일반)"],
    },
    {
        "id": "heart",
        "label": "심장·기력",
        "hint": "실신, 운동 기피",
        "department_keywords": ["심장", "내과", "응급"],
    },
    {
        "id": "trauma",
        "label": "외상·출혈",
        "hint": "사고, 상처, 출혈",
        "department_keywords": ["응급", "외과"],
    },
    {
        "id": "wellness",
        "label": "예방·중성화",
        "hint": "접종, 건강검진",
        "department_keywords": ["예방접종", "중성화", "일반진료", "건강검진"],
    },
    {
        "id": "unknown",
        "label": "잘 모르겠음",
        "hint": "증상만으로 판단이 어려움",
        "department_keywords": [],
    },
]

# Severity buttons → care_level set + whether to force/prefer 24h
# Inspired by Vetster teletriage 4-bucket outcomes (emergency now → can wait)
SEVERITIES: list[dict[str, Any]] = [
    {
        "id": "mild",
        "label": "경미",
        "hint": "조금 불편해 보임 · 기다려도 됨",
        "care_levels": ["neighborhood", "primary", "secondary", "university", "rehab_specialty"],
        "force_24h": False,
        "prefer_emergency_dept": False,
        "default_radius_km": 5,
    },
    {
        "id": "moderate",
        "label": "걱정됨",
        "hint": "오늘 안에 보는 게 좋음",
        "care_levels": ["primary", "secondary", "university"],
        "force_24h": False,
        "prefer_emergency_dept": False,
        "default_radius_km": 8,
    },
    {
        "id": "severe",
        "label": "중증·응급",
        "hint": "바로 가야 할 것 같음",
        "care_levels": ["secondary", "university", "primary"],
        "force_24h": False,
        "prefer_emergency_dept": True,
        "default_radius_km": 15,
    },
]


def resolve_filters(
    *,
    symptom_id: str | None,
    severity_id: str | None,
    need_24h: bool,
) -> dict[str, Any]:
    symptom = next((s for s in SYMPTOMS if s["id"] == symptom_id), None)
    severity = next((s for s in SEVERITIES if s["id"] == severity_id), None) or SEVERITIES[1]

    force_24h = bool(need_24h) or bool(severity.get("force_24h"))
    # Severe trauma/breath → nudge 24h preference without hard-forcing unless user toggled
    soft_24h_symptoms = {"trauma", "breath", "heart"}
    prefer_24h = force_24h or (
        severity["id"] == "severe" and (symptom_id in soft_24h_symptoms)
    )

    radius = float(severity["default_radius_km"])
    if prefer_24h:
        radius = max(radius, 12.0)

    return {
        "department_keywords": list((symptom or {}).get("department_keywords") or []),
        "care_levels": list(severity["care_levels"]),
        "need_24h": force_24h,
        "prefer_24h": prefer_24h,
        "prefer_emergency_dept": bool(severity.get("prefer_emergency_dept")),
        "radius_km": radius,
        "symptom": symptom,
        "severity": severity,
    }


CITY_PRESETS: list[dict[str, Any]] = [
    {"id": "seoul-gangnam", "label": "서울 강남", "lat": 37.4979, "lng": 127.0276},
    {"id": "seoul-mapo", "label": "서울 마포", "lat": 37.5663, "lng": 126.9019},
    {"id": "busan-haeundae", "label": "부산 해운대", "lat": 35.1631, "lng": 129.1635},
    {"id": "daegu-suseong", "label": "대구 수성", "lat": 35.8583, "lng": 128.6306},
    {"id": "incheon-yeonsu", "label": "인천 연수", "lat": 37.4100, "lng": 126.6780},
    {"id": "gwangju-seo", "label": "광주 서구", "lat": 35.1520, "lng": 126.8895},
    {"id": "daejeon-yuseong", "label": "대전 유성", "lat": 36.3620, "lng": 127.3560},
    {"id": "suwon", "label": "수원", "lat": 37.2636, "lng": 127.0286},
]
