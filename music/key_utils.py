"""Key signatures, transposition, and practical diatonic seventh chords."""

from __future__ import annotations

import re

from music.chord_parser import NOTE_MAP

KEY_TO_PC = {
    "C": 0, "G": 7, "D": 2, "A": 9, "E": 4, "B": 11,
    "F#": 6, "C#": 1,
    "F": 5, "Bb": 10, "Eb": 3, "Ab": 8, "Db": 1, "Gb": 6, "Cb": 11,
}

KEY_ALIASES = {"A#": "Bb", "D#": "Eb", "G#": "Ab", "C#": "Db", "F#": "Gb"}

FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
SHARP_KEYS = {"G", "D", "A", "E", "B", "F#", "C#"}

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

LILYPOND_KEYS = {
    "C": "c", "G": "g", "D": "d", "A": "a", "E": "e", "B": "b",
    "F#": "fis", "C#": "cis", "F": "f", "Bb": "bes", "Eb": "ees",
    "Ab": "aes", "Db": "des", "Gb": "ges", "Cb": "ces",
}

LILYPOND_SHARP_NOTE_NAMES = ["c", "cis", "d", "dis", "e", "f", "fis", "g", "gis", "a", "ais", "b"]
LILYPOND_FLAT_NOTE_NAMES = ["c", "des", "d", "ees", "e", "f", "ges", "g", "aes", "a", "bes", "b"]

MAJOR_SCALE_INTERVALS = [0, 2, 4, 5, 7, 9, 11]
DIATONIC_7TH_QUALITIES = ["maj7", "m7", "m7", "maj7", "7", "m7", "m7b5"]


def normalize_key(key: str | None) -> str:
    key = (key or "C").strip()
    if not key:
        return "C"
    key = key[0].upper() + key[1:]
    return key if key in KEY_TO_PC else KEY_ALIASES.get(key, "C")


def key_delta_semitones(old_key: str | None, new_key: str | None) -> int:
    old = normalize_key(old_key)
    new = normalize_key(new_key)
    return (KEY_TO_PC[new] - KEY_TO_PC[old]) % 12


def prefer_flats_for_key(key: str | None) -> bool:
    return normalize_key(key) in FLAT_KEYS


def note_name_for_pc(pc: int, key: str | None = "C") -> str:
    names = FLAT_NAMES if prefer_flats_for_key(key) else SHARP_NAMES
    return names[pc % 12]


def lilypond_key_name(key: str | None = "C") -> str:
    return LILYPOND_KEYS[normalize_key(key)]


def lilypond_note_name_for_pc(pc: int, key: str | None = "C") -> str:
    names = LILYPOND_FLAT_NOTE_NAMES if prefer_flats_for_key(key) else LILYPOND_SHARP_NOTE_NAMES
    return names[pc % 12]


def transpose_note_name(note: str, semitones: int, key: str | None = "C") -> str:
    note = (note or "C").strip()
    # KEY_TO_PC only lists key names; chord roots like D#, G#, or E# are
    # valid to the parser and must still transpose.
    pc = KEY_TO_PC.get(note)
    if pc is None:
        pc = NOTE_MAP.get(note)
    if pc is None:
        return note
    return note_name_for_pc(pc + semitones, key)


def transpose_chord_symbol(symbol: str, semitones: int, target_key: str | None = "C") -> str:
    """Transpose only the root and slash bass note, preserving the chord quality text."""
    symbol = (symbol or "").strip()
    if not symbol:
        return ""
    match = re.match(r"^([A-G](?:#|b)?)(.*)$", symbol)
    if not match:
        return symbol
    root, rest = match.groups()
    new_root = transpose_note_name(root, semitones, target_key)

    if "/" in rest:
        before, slash = rest.rsplit("/", 1)
        bass_match = re.match(r"^([A-G](?:#|b)?)(.*)$", slash)
        if bass_match:
            bass, tail = bass_match.groups()
            slash = transpose_note_name(bass, semitones, target_key) + tail
        rest = before + "/" + slash
    return new_root + rest


# Transposing instruments: written pitch = concert pitch + semitones.
# A concert C sounds when an E♭ alto player reads an A (9 semitones up).
# Octave-displaced entries (tenor, bari) keep written parts in staff range.
TRANSPOSING_INSTRUMENTS = {
    "concert": {"label": "Concert Pitch", "semitones": 0},
    "bb": {"label": "B♭ — Trumpet, Clarinet, Soprano Sax", "semitones": 2},
    "bb_tenor": {"label": "B♭ — Tenor Sax", "semitones": 14},
    "eb_alto": {"label": "E♭ — Alto Sax", "semitones": 9},
    "eb_bari": {"label": "E♭ — Baritone Sax", "semitones": 21},
    "f_horn": {"label": "F — French Horn", "semitones": 7},
}

# Preferred enharmonic spelling per pitch class for major key signatures.
PREFERRED_MAJOR_KEYS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def normalize_transposition(instrument: str | None) -> str:
    instrument = (instrument or "concert").strip().lower()
    return instrument if instrument in TRANSPOSING_INSTRUMENTS else "concert"


def transposed_key_sig(key: str | None, semitones: int) -> str:
    """The written key signature for a part transposed up by `semitones`."""
    key = normalize_key(key)
    if semitones % 12 == 0:
        return key
    return PREFERRED_MAJOR_KEYS[(KEY_TO_PC[key] + semitones) % 12]


def diatonic_seventh_chords(key: str | None = "C") -> list[str]:
    """Return I through vii seventh chords for a major key."""
    key = normalize_key(key)
    root_pc = KEY_TO_PC[key]
    return [note_name_for_pc(root_pc + interval, key) + quality for interval, quality in zip(MAJOR_SCALE_INTERVALS, DIATONIC_7TH_QUALITIES)]
