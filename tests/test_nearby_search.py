from app.hospitals import search_nearby, stats
from app.triage import resolve_filters


def test_gangnam_severe_24h():
    f = resolve_filters(symptom_id="trauma", severity_id="severe", need_24h=True)
    rows = search_nearby(
        lat=37.4979,
        lng=127.0276,
        radius_km=f["radius_km"],
        need_24h=True,
        care_levels=f["care_levels"],
        department_keywords=f["department_keywords"],
        prefer_emergency_dept=True,
        limit=5,
    )
    assert rows
    assert all(r["is_24h"] for r in rows)
    # 24h / emergency float to top
    assert rows[0]["priority"] >= rows[-1]["priority"]


def test_mild_neighborhood_possible():
    f = resolve_filters(symptom_id="wellness", severity_id="mild", need_24h=False)
    rows = search_nearby(
        lat=37.4979,
        lng=127.0276,
        radius_km=f["radius_km"],
        need_24h=False,
        care_levels=f["care_levels"],
        department_keywords=f["department_keywords"],
        limit=10,
    )
    assert rows


def test_emergency_sorted_first():
    rows = search_nearby(
        lat=37.5665,
        lng=126.978,
        radius_km=15,
        limit=30,
    )
    assert rows
    featured = [r for r in rows if r["is_24h"] or r["is_emergency"]]
    if featured:
        assert rows[0]["priority"] >= 1
        # featured block should precede non-featured in sort
        first_plain = next((i for i, r in enumerate(rows) if r["priority"] == 0), None)
        if first_plain is not None:
            assert all(r["priority"] >= 1 for r in rows[:first_plain])


def test_stats_has_care_levels():
    s = stats()
    assert s["total_with_coords"] > 1000
    assert "university" in s["by_care_level"] or "primary" in s["by_care_level"]
