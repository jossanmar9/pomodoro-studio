import pytest

from app.services.timer import SegmentType, build_chapters, build_timeline, format_timestamp


def test_standard_two_hour_25_5_timeline() -> None:
    timeline = build_timeline(25, 5, 120)
    assert timeline.sessions == 4
    assert timeline.focus_seconds == 100 * 60
    assert timeline.break_seconds == 20 * 60
    assert timeline.total_seconds == 120 * 60


def test_timeline_never_exceeds_target() -> None:
    timeline = build_timeline(25, 5, 61)
    assert timeline.total_seconds == 61 * 60
    assert timeline.segments[-1].kind is SegmentType.FOCUS
    assert timeline.segments[-1].duration_seconds == 60


def test_zero_break_is_supported() -> None:
    timeline = build_timeline(25, 0, 50)
    assert timeline.sessions == 2
    assert all(segment.kind is SegmentType.FOCUS for segment in timeline.segments)


def test_invalid_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        build_timeline(0, 5, 120)
    with pytest.raises(ValueError):
        build_timeline(25, -1, 120)
    with pytest.raises(ValueError):
        build_timeline(25, 5, 0)


def test_chapters_match_timeline() -> None:
    chapters = build_chapters(build_timeline(25, 5, 60))
    assert chapters.splitlines() == [
        "00:00:00 Sessió 1",
        "00:25:00 Descans",
        "00:30:00 Sessió 2",
        "00:55:00 Descans",
    ]


def test_english_chapters_match_timeline() -> None:
    chapters = build_chapters(build_timeline(25, 5, 60), language="en")
    assert chapters.splitlines() == [
        "00:00:00 Focus session 1",
        "00:25:00 Break",
        "00:30:00 Focus session 2",
        "00:55:00 Break",
    ]


def test_timestamp_format() -> None:
    assert format_timestamp(3661) == "01:01:01"
