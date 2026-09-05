"""Aebersold-style chord-scale helpers for optional horizontal continuity.

This is not a rigid implementation of the full Scale Syllabus.  It gives the
melody and bass generators a practical pool of scale material that contains the
chord tones and fits common jazz-function categories: major, dominant, minor,
half-diminished, diminished, and altered dominant.
"""

from __future__ import annotations

from music.chord_parser import parse_chord_details, parse_chord, NOTE_MAP

# Intervals are in semitones from the chord root.  The names intentionally use
# familiar teaching labels so future UI/tooltips can expose them.
SCALE_LIBRARY: dict[str, list[tuple[str, list[int]]]] = {
    "major": [
        ("Major", [0, 2, 4, 5, 7, 9, 11]),
        ("Lydian", [0, 2, 4, 6, 7, 9, 11]),
        ("Major pentatonic", [0, 2, 4, 7, 9]),
        ("Bebop major", [0, 2, 4, 5, 7, 8, 9, 11]),
    ],
    "dominant": [
        ("Mixolydian", [0, 2, 4, 5, 7, 9, 10]),
        ("Bebop dominant", [0, 2, 4, 5, 7, 9, 10, 11]),
        ("Lydian dominant", [0, 2, 4, 6, 7, 9, 10]),
        ("Dominant pentatonic", [0, 2, 4, 7, 10]),
    ],
    "dominant_b9": [
        ("Spanish/Jewish", [0, 1, 4, 5, 7, 8, 10]),
        ("Half-whole diminished", [0, 1, 3, 4, 6, 7, 9, 10]),
        ("Altered", [0, 1, 3, 4, 6, 8, 10]),
    ],
    "dominant_alt": [
        ("Altered", [0, 1, 3, 4, 6, 8, 10]),
        ("Half-whole diminished", [0, 1, 3, 4, 6, 7, 9, 10]),
        ("Whole tone", [0, 2, 4, 6, 8, 10]),
    ],
    "minor": [
        ("Dorian", [0, 2, 3, 5, 7, 9, 10]),
        ("Minor pentatonic", [0, 3, 5, 7, 10]),
        ("Bebop minor", [0, 2, 3, 4, 5, 7, 9, 10]),
    ],
    "half-diminished": [
        ("Locrian", [0, 1, 3, 5, 6, 8, 10]),
        ("Locrian natural 2", [0, 2, 3, 5, 6, 8, 10]),
    ],
    "diminished": [
        ("Whole-half diminished", [0, 2, 3, 5, 6, 8, 9, 11]),
    ],
}


def _category(symbol: str) -> str:
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return "major"
    lowered = (symbol or "").lower()
    ints = {i % 12 for i in parsed.intervals}
    if parsed.quality == "half-diminished":
        return "half-diminished"
    if parsed.quality == "diminished":
        return "diminished"
    if parsed.quality == "minor":
        return "minor"
    if parsed.quality == "altered" or "alt" in lowered:
        return "dominant_alt"
    if 4 in ints and 10 in ints:
        if "b9" in lowered or "#9" in lowered:
            return "dominant_b9"
        if any(token in lowered for token in ("#5", "b5", "#11", "+4", "b13")):
            return "dominant_alt"
        return "dominant"
    return "major"


def scale_choices(symbol: str) -> list[tuple[str, list[int]]]:
    """Return practical scale choices, with chord tones guaranteed in each."""
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return []
    root = NOTE_MAP[parsed.root]
    chord_tone_pcs = {(root + i) % 12 for i in parsed.intervals}
    choices = []
    for name, intervals in SCALE_LIBRARY.get(_category(symbol), SCALE_LIBRARY["major"]):
        pcs = {(root + i) % 12 for i in intervals}
        pcs |= chord_tone_pcs
        choices.append((name, sorted(pcs)))
    return choices


def scale_focus_notes(symbol: str, octave: int = 4, rng=None) -> list[int]:
    """Return a MIDI note pool for optional scale-focused generation.

    If an rng is supplied, one fitting scale choice is selected per chord so a
    phrase has horizontal identity.  Without rng, the first practical choice is
    used for deterministic tests.
    """
    choices = scale_choices(symbol)
    if not choices:
        return parse_chord(symbol, octave)
    name, pcs = rng.choice(choices) if rng is not None else choices[0]
    base_c = (octave + 1) * 12
    return [base_c + pc for pc in pcs]
