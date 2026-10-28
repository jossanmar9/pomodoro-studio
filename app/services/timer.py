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
    """Construeix una línia temporal Pomodoro sense superar la duració demanada."""
    if focus_minutes <= 0:
        raise ValueError("focus_minutes ha de ser major que zero")
    if break_minutes < 0:
        raise ValueError("break_minutes no pot ser negatiu")
    if total_minutes <= 0:
        raise ValueError("total_minutes ha de ser major que zero")

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


def build_chapters(timeline: TimelineSummary, language: str = "va") -> str:
    """Genera capítols per a la UI (valencià) o la publicació (anglés)."""
    if language not in {"va", "en"}:
        raise ValueError("Idioma de capítols no compatible")
    lines: list[str] = []
    for segment in timeline.segments:
        if language == "en":
            label = f"Focus session {segment.session}" if segment.kind is SegmentType.FOCUS else "Break"
        else:
            label = f"Sessió {segment.session}" if segment.kind is SegmentType.FOCUS else "Descans"
        lines.append(f"{format_timestamp(segment.start_seconds)} {label}")
    return "\n".join(lines)
