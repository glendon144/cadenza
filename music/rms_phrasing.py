"""Playback-only RMS-inspired expressive phrasing.

This module adapts Glen's ECM/RMS speech-timing idea to note events.  It does
not change printed notation.  It only nudges solo-note playback timing inside
phrases: phrases begin a little relaxed, then catch up so their endpoints stay
on time.
"""

from __future__ import annotations

import math
from typing import Iterable


def _phrase_groups(events: list[dict], gap_threshold: float = 0.75) -> list[list[dict]]:
    ordered = sorted((dict(e) for e in events), key=lambda e: (float(e.get("start", 0.0)), float(e.get("pitch", 0))))
    groups: list[list[dict]] = []
    current: list[dict] = []
    last_end: float | None = None
    for event in ordered:
        start = float(event.get("start", 0.0))
        dur = max(0.01, float(event.get("duration", 0.25)))
        if current and last_end is not None and start - last_end >= gap_threshold:
            groups.append(current)
            current = []
        current.append(event)
        last_end = max(last_end if last_end is not None else start, start + dur)
    if current:
        groups.append(current)
    return groups


def _depth_for_tempo(tempo: int, intensity: float) -> float:
    """Return maximum normalized midpoint lag for a phrase.

    The lag is intentionally modest.  Slow phrases can breathe more; faster
    bebop lines should stay close to the grid.
    """
    tempo = max(40, min(320, int(tempo or 120)))
    intensity = max(0.0, min(1.0, float(intensity)))
    if tempo <= 90:
        base = 0.085
    elif tempo <= 140:
        base = 0.065
    elif tempo <= 200:
        base = 0.045
    else:
        base = 0.025
    return base * intensity


def warp_solo_events(events: Iterable[dict], tempo: int = 120, intensity: float = 1.0) -> list[dict]:
    """Apply endpoint-preserving expressive rubato to solo note events.

    Each phrase uses a lag curve: normalized_time + depth * sin(pi*t).  That
    means the line starts slightly behind, reaches maximum relaxation near the
    middle, then accelerates back to the scheduled endpoint.  This mirrors the
    ECM/RMS idea of flexible intra-phrase timing while finishing on time.
    """
    source = [dict(e) for e in events]
    if not source:
        return []
    depth = _depth_for_tempo(tempo, intensity)
    if depth <= 0.0001:
        return source

    warped: list[dict] = []
    for group in _phrase_groups(source):
        if len(group) < 3:
            warped.extend(group)
            continue
        phrase_start = min(float(e.get("start", 0.0)) for e in group)
        phrase_end = max(float(e.get("start", 0.0)) + max(0.01, float(e.get("duration", 0.25))) for e in group)
        phrase_dur = max(0.01, phrase_end - phrase_start)
        max_lag_beats = min(0.18, phrase_dur * depth)

        group_sorted = sorted(group, key=lambda e: (float(e.get("start", 0.0)), int(e.get("pitch", 0))))
        new_starts: list[float] = []
        for event in group_sorted:
            old_start = float(event.get("start", 0.0))
            t = max(0.0, min(1.0, (old_start - phrase_start) / phrase_dur))
            lag = max_lag_beats * math.sin(math.pi * t)
            new_starts.append(old_start + lag)

        # Preserve ordering and keep events inside phrase boundaries.
        for i, event in enumerate(group_sorted):
            old_start = float(event.get("start", 0.0))
            old_dur = max(0.01, float(event.get("duration", 0.25)))
            new_start = max(phrase_start, min(new_starts[i], phrase_end - 0.01))
            if i + 1 < len(group_sorted):
                next_start = new_starts[i + 1]
                max_dur = max(0.04, next_start - new_start - 0.01)
            else:
                max_dur = max(0.04, phrase_end - new_start)
            event["start"] = new_start
            event["duration"] = max(0.04, min(old_dur * 0.97, max_dur))
            event["rms_phrased"] = True
            warped.append(event)

    return sorted(warped, key=lambda e: (float(e.get("start", 0.0)), int(e.get("pitch", 0))))
