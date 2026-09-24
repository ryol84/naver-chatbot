from app.hours_format import format_hours


def test_format_24h():
    h = format_hours(hours_24h="yes", weekday_hours="00:00–24:00", weekend_hours=None)
    assert h["is_24h"] is True
    assert h["lines"] == ["24시간 영업"]
    assert h["unknown"] is False


def test_format_weekday_weekend_split():
    h = format_hours(
        hours_24h="no",
        weekday_hours="10:00–19:00",
        weekend_hours="토 10:00–17:00 · 일 휴무",
    )
    assert h["weekday"] == "10:00–19:00"
    assert h["saturday"] == "10:00–17:00"
    assert h["sunday"] == "휴무"
    assert h["lines"] == ["평일 10:00–19:00", "토 10:00–17:00", "일 휴무"]


def test_format_unknown():
    h = format_hours(hours_24h="unknown", weekday_hours=None, weekend_hours=None)
    assert h["unknown"] is True
    assert "정보 없음" in h["lines"][0]


def test_format_tilde_normalized():
    h = format_hours(hours_24h="no", weekday_hours="09:00~18:00", weekend_hours="토 휴무 · 일 휴무")
    assert h["weekday"] == "09:00–18:00"
    assert h["saturday"] == "휴무"
    assert h["sunday"] == "휴무"
