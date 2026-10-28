from dataclasses import dataclass
from enum import Enum


class SegmentType(str, Enum):
    FOCUS = "FOCUS"
    BREAK = "BREAK"


@dataclass(frozen=True)
class TimelineSegment:
    kind: SegmentType
    session: int
    start_seconds: int
    duration_seconds: int

    @property
    def end_seconds(self) -> int:
        return self.start_seconds + self.duration_seconds


@dataclass(frozen=True)
class TimelineSummary:
    segments: list[TimelineSegment]
    sessions: int
    focus_seconds: int
    break_seconds: int
    total_seconds: int


def build_timeline(focus_minutes: int, break_minutes: int, total_minutes: int) -> TimelineSummary:
    """Build a Pomodoro timeline that never exceeds the requested duration.

    A final focus segment may be shorter than the configured focus interval so the
    generated media can end exactly at the requested duration. A break is added
    only when time remains for it after a focus segment.
    """
    if focus_minutes <= 0:
        raise ValueError("focus_minutes must be greater than zero")
    if break_minutes < 0:
        raise ValueError("break_minutes cannot be negative")
    if total_minutes <= 0:
        raise ValueError("total_minutes must be greater than zero")

    focus = focus_minutes * 60
    pause = break_minutes * 60
    target = total_minutes * 60
    cursor = 0
    session = 1
    segments: list[TimelineSegment] = []

    while cursor < target:
        focus_duration = min(focus, target - cursor)
        segments.append(TimelineSegment(SegmentType.FOCUS, session, cursor, focus_duration))
        cursor += focus_duration
        if cursor >= target:
            break

        break_duration = min(pause, target - cursor)
        if break_duration:
            segments.append(TimelineSegment(SegmentType.BREAK, session, cursor, break_duration))
            cursor += break_duration
        session += 1

    focus_total = sum(s.duration_seconds for s in segments if s.kind is SegmentType.FOCUS)
    break_total = sum(s.duration_seconds for s in segments if s.kind is SegmentType.BREAK)
    sessions = sum(1 for s in segments if s.kind is SegmentType.FOCUS)
    return TimelineSummary(segments, sessions, focus_total, break_total, cursor)


def format_timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_chapters(timeline: TimelineSummary) -> str:
    lines: list[str] = []
    for segment in timeline.segments:
        label = f"Session {segment.session}" if segment.kind is SegmentType.FOCUS else "Break"
        lines.append(f"{format_timestamp(segment.start_seconds)} {label}")
    return "\n".join(lines)
