"""Geocode helpers — short label formatting (no live network)."""

from app.geocode import _short_label


def test_short_label_hapjeong():
    hit = {
        "name": "합정동",
        "display_name": "합정동, 마포구, 서울특별시, 대한민국",
        "address": {
            "suburb": "합정동",
            "borough": "마포구",
            "city": "서울특별시",
            "country": "대한민국",
        },
    }
    assert _short_label(hit, "서울 마포구 합정동") == "서울 마포구 합정동"


def test_short_label_fallback_name():
    hit = {"name": "해운대", "display_name": "해운대, 부산"}
    assert _short_label(hit, "부산") == "해운대"
