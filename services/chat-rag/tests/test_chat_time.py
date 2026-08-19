from datetime import datetime, timedelta, timezone

from app.routers.chat import _utc_iso


def test_utc_iso_marks_naive_mongo_datetime_as_utc():
    assert _utc_iso(datetime(2026, 8, 19, 12, 30)) == "2026-08-19T12:30:00Z"


def test_utc_iso_converts_aware_datetime_to_utc():
    colombo = timezone(timedelta(hours=5, minutes=30))
    assert _utc_iso(datetime(2026, 8, 19, 18, 0, tzinfo=colombo)) == "2026-08-19T12:30:00Z"
