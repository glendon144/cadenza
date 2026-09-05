"""Idiomatic piano voicings for chord symbols."""

from __future__ import annotations

from music.chord_parser import parse_chord_details, root_midi
from music.groove import normalize_style


def _degree_note(root: int, interval: int, target_min=60, target_max=76) -> int:
    note = root + interval
    while note < target_min:
        note += 12
    while note > target_max:
        note -= 12
    return note


def _shell_intervals(intervals: list[int]) -> list[int]:
    # Rootless jazz voicing priority: 3rd, 7th, then useful color tones.
    thirds = [i for i in intervals if i % 12 in (3, 4)]
    sevenths = [i for i in intervals if i % 12 in (9, 10, 11)]
    colors = [i for i in intervals if i >= 13 and i % 12 not in (0, 3, 4, 7)]

    chosen: list[int] = []
    if thirds:
        chosen.append(thirds[0])
    if sevenths:
        chosen.append(sevenths[0])
    for i in colors:
        if len(chosen) >= 4:
            break
        chosen.append(i)

    if len(chosen) < 2:
        for i in intervals:
            if i != 0 and i not in chosen:
                chosen.append(i)
            if len(chosen) >= 3:
                break
    return chosen


def voice_chord(symbol: str, style: str = "jazz") -> dict:
    style = normalize_style(style)
    if not symbol or symbol.strip() in {"/", "%", "-"}:
        return {"left": [], "right": []}

    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return {"left": [], "right": []}

    bass = root_midi(symbol, octave=2, prefer_slash_bass=True)
    left = [bass]
    if style != "jazz" and 7 in parsed.intervals:
        left.append(bass + 7)

    root4 = root_midi(symbol, octave=4, prefer_slash_bass=False)
    if style == "jazz":
        right = [_degree_note(root4, i) for i in _shell_intervals(parsed.intervals)]
    elif style in {"bossa", "samba"}:
        right = [_degree_note(root4, i, 60, 79) for i in parsed.intervals if i != 0][:4]
    else:
        right = [_degree_note(root4, i, 60, 79) for i in parsed.intervals if i != 0][:3]

    return {"left": sorted(set(left)), "right": sorted(set(right))}
