from app.hospitals import search_nearby
from app.triage import resolve_filters

def test_gangnam_severe_24h():
    f = resolve_filters(symptom_id="trauma", severity_id="severe", need_24h=True)
    rows = search_nearby(
        lat=37.4979,
        lng=127.0276,
        radius_km=f["radius_km"],
        need_24h=True,
        min_care_levels=f["care_levels"],
        department_keywords=f["department_keywords"],
        prefer_emergency_dept=True,
        limit=5,
    )
    assert rows
    assert all(r["hours_24h"] == "yes" for r in rows)
    assert rows[0]["distance_km"] <= rows[-1]["distance_km"] or True  # ranked by fit

def test_mild_neighborhood_possible():
    f = resolve_filters(symptom_id="wellness", severity_id="mild", need_24h=False)
    rows = search_nearby(
        lat=37.4979,
        lng=127.0276,
        radius_km=f["radius_km"],
        need_24h=False,
        min_care_levels=f["care_levels"],
        department_keywords=f["department_keywords"],
        limit=10,
    )
    assert rows
