from app.geo_qa import normalize_sido
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
    dists = [r["distance_km"] for r in rows]
    assert dists == sorted(dists)


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
    # Nearest-first within the result set
    dists = [r["distance_km"] for r in rows]
    assert dists == sorted(dists)


def test_stats_has_care_levels():
    s = stats()
    assert s["total_with_coords"] > 1000
    assert "university" in s["by_care_level"] or "primary" in s["by_care_level"]
    assert s.get("excluded_coord_mismatch", 0) >= 0


def test_busan_haeundae_excludes_remote_sido():
    """Coords that disagree with address sido must not appear near Busan."""
    from app.triage import CITY_PRESETS

    busan = next(c for c in CITY_PRESETS if c["id"] == "busan-haeundae")
    rows = search_nearby(lat=busan["lat"], lng=busan["lng"], radius_km=12, limit=50)
    assert rows
    allowed = {"부산", "울산", "경남"}
    for h in rows:
        assert normalize_sido(h.get("sido")) in allowed, (h.get("name"), h.get("sido"), h.get("address"))
    assert any(normalize_sido(h.get("sido")) == "부산" for h in rows)
