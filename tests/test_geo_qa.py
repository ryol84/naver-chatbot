"""Regression: wrong geocodes must never appear near city chips."""
from __future__ import annotations

from app.geo_qa import coords_plausible_for_row, normalize_sido, sido_from_address
from app.hospitals import load_hospitals, search_nearby, stats
from app.triage import CITY_PRESETS

# Expected local sido prefixes per city chip
_CHIP_ALLOWED = {
    "seoul-gangnam": ("서울", "경기", "인천"),
    "seoul-mapo": ("서울", "경기", "인천"),
    "busan-haeundae": ("부산", "울산", "경남"),
    "daegu-suseong": ("대구", "경북", "경남"),
    "incheon-yeonsu": ("인천", "경기", "서울"),
    "gwangju-seo": ("광주", "전남", "전북"),
    "daejeon-yuseong": ("대전", "세종", "충남", "충북"),
    "suwon": ("경기", "서울", "인천"),
}

_REMOTE_KW = ("강원", "충남", "충청남", "충북", "충청북", "제주", "전남", "전북", "경북")


def test_known_bad_rows_rejected():
    """User-reported mismatches must fail QA."""
    bad = [
        {
            "name": "24시 연산동물의료센터",
            "sido": "강원",
            "sigungu": "태백시",
            "address": "강원 태백시 황지로 9 2주공후문",
            "lat": 35.17495346,
            "lng": 129.085556,
        },
        {
            "name": "더프라임동물의료원",
            "sido": "충청남도",
            "sigungu": "금산군",
            "address": "충청남도 금산군 추부면 산내로 22-8",
            "lat": 35.1424942,
            "lng": 129.1080627,
        },
        {
            "name": "센텀동물메디컬센터 수영점",
            "sido": "제주특별자치도",
            "sigungu": "서귀포시",
            "address": "제주특별자치도 서귀포시 성산읍 고성중앙로 28-7",
            "lat": 35.16850281,
            "lng": 129.1138916,
        },
        {
            "name": "아크리스동물의료센터",
            "sido": "강원",
            "sigungu": "삼척시",
            "address": "강원 삼척시 새천년도로 469-1 1층",
            "lat": 37.51371384,
            "lng": 127.0619125,
        },
        {
            "name": "부산종합동물병원",
            "sido": "경상남도",
            "sigungu": "통영시",
            "address": "경상남도 통영시 욕지면 제암길 24",
            "lat": 35.16857529,
            "lng": 129.0667877,
        },
        {
            "name": "닥터주 동물병원",
            "sido": "경상남도",
            "sigungu": "양산시",
            "address": "경상남도 양산시 하북면 백록로 34",
            "lat": 35.16302109,
            "lng": 129.1777344,
        },
    ]
    for row in bad:
        assert not coords_plausible_for_row(row), row["name"]


def test_good_busan_row_accepted():
    good = {
        "name": "해운대동물메디컬센터",
        "sido": "부산광역시",
        "sigungu": "해운대구",
        "address": "부산광역시 해운대구 양운로 40 (좌동)",
        "lat": 35.16723633,
        "lng": 129.1777802,
    }
    assert coords_plausible_for_row(good)


def test_sido_helpers():
    assert normalize_sido("부산광역시") == "부산"
    assert normalize_sido("강원특별자치도") == "강원"
    assert sido_from_address("강원 태백시 황지로 9") == "강원"
    assert sido_from_address("부산광역시 해운대구 양운로 40") == "부산"


def test_all_city_chips_local_only():
    for city in CITY_PRESETS:
        allowed = _CHIP_ALLOWED.get(city["id"])
        assert allowed, city["id"]
        rows = search_nearby(lat=city["lat"], lng=city["lng"], radius_km=15, limit=60)
        assert rows, city["label"]
        for h in rows:
            norm = normalize_sido(h.get("sido"))
            assert norm in allowed, (city["label"], h.get("name"), h.get("sido"), h.get("address"))


def test_busan_haeundae_no_remote_address_keywords():
    busan = next(c for c in CITY_PRESETS if c["id"] == "busan-haeundae")
    rows = search_nearby(lat=busan["lat"], lng=busan["lng"], radius_km=15, limit=80)
    assert rows
    for h in rows:
        addr = h.get("address") or ""
        for kw in ("강원", "충남", "충청남", "제주", "서울", "경기"):
            assert kw not in addr, (h.get("name"), addr)


def test_loaded_set_has_no_centroid_outliers():
    """Every loaded row with a known city centroid must sit within 50km."""
    from app.geo_qa import _CITY_CENTROID, _CITY_MAX_KM, normalize_sido, _haversine_km

    outliers = []
    for h in load_hospitals():
        sido = normalize_sido(h.get("sido"))
        sg = (h.get("sigungu") or "").strip()
        if not sido or not sg:
            continue
        cen = _CITY_CENTROID.get((sido, sg))
        if not cen:
            continue
        d = _haversine_km(cen[0], cen[1], float(h["lat"]), float(h["lng"]))
        if d > _CITY_MAX_KM:
            outliers.append((d, h.get("name"), sido, sg))
    assert not outliers, outliers[:5]


def test_stats_reports_exclusions():
    s = stats()
    assert s["excluded_coord_mismatch"] >= 400
    assert s["total_with_coords"] >= 3000
