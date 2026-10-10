"""Rule-based chord parser for ChordCraft.

The parser favors practical jazz symbols over music-theory completeness.  It
returns MIDI notes, validation errors, and scale material for the generator.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from dataclasses import dataclass

NOTE_MAP = {
    "C": 0, "B#": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7,
    "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
}



FLAT_PC_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
SHARP_PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def pc_for_note(note: str) -> int | None:
    return NOTE_MAP.get(note)

def note_name_for_pc(pc: int, prefer_flats: bool = True) -> str:
    names = FLAT_PC_NAMES if prefer_flats else SHARP_PC_NAMES
    return names[pc % 12]

def root_pc(symbol: str) -> int | None:
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return None
    return NOTE_MAP.get(parsed.root)

def is_dominant_chord(symbol: str) -> bool:
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return False
    intervals_mod = {i % 12 for i in parsed.intervals}
    # Dominant function needs a major third and minor seventh.  Altered chords
    # produced by the parser also carry those tones.
    return 4 in intervals_mod and 10 in intervals_mod and parsed.quality not in {"minor", "diminished", "half-diminished"}

def tritone_sub_symbol(symbol: str, prefer_flats: bool = True) -> str | None:
    """Return a practical tritone substitute symbol for a dominant chord.

    G7 -> Db7, C13 -> Gb13, F7alt -> B7alt.  The visible chart still keeps
    the user's original chord; this helper is for optional bass/melody color.
    """
    if not is_dominant_chord(symbol):
        return None
    m = re.match(r"^([A-G](?:#|b)?)(.*)$", (symbol or '').strip())
    if not m:
        return None
    pc = NOTE_MAP[m.group(1)]
    return note_name_for_pc(pc + 6, prefer_flats=prefer_flats) + (m.group(2) or '')

DEGREE_TO_INTERVAL = {2: 2, 4: 5, 5: 7, 6: 9, 7: 10, 9: 14, 11: 17, 13: 21}

@dataclass(frozen=True)
class ParsedChord:
    root: str
    intervals: list[int]
    bass: str | None = None
    quality: str = "major"


def _clean_suffix(rest: str) -> str:
    return (
        rest.strip()
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("∆", "Δ")
    )


def _dedupe_sorted(intervals: list[int]) -> list[int]:
    return sorted(set(intervals))


def parse_chord_details(symbol: str) -> tuple[ParsedChord | None, str | None]:
    symbol = (symbol or "").strip().replace("♭", "b").replace("♯", "#").replace("−", "-")
    if symbol:
        symbol = symbol[0].upper() + symbol[1:]
    if not symbol:
        return None, "Enter a chord symbol."
    if symbol in {"/", "%", "-"}:
        return None, "Enter a chord symbol, such as Cmaj7 or G7."

    m = re.match(r"^([A-G](?:#|b)?)(.*)$", symbol)
    if not m:
        return None, "Chord must start with A-G, optionally followed by # or b."

    root = m.group(1)
    rest = _clean_suffix(m.group(2))
    # 6/9 chords use a slash that is not a bass note: C6/9 means C69.
    rest = rest.replace("6/9", "69")
    rest = re.sub(r"major|Maj|MAJ", "maj", rest)
    rest = re.sub(r"minor|Minor|MIN|min", "m", rest)
    rest = re.sub(r"^o(?=7|$)", "dim", rest)
    rest = rest.replace("ø7", "ø")
    rest = re.sub(r"^(maj|M)(?=$|/)", "", rest)
    rest = re.sub(r"Δ(?=$|/)", "maj7", rest)
    rest = re.sub(r"^(m|-)(M|Δ)(?=7|9|11|13)", r"\1maj", rest)
    bass = None
    if "/" in rest:
        rest, bass = rest.split("/", 1)
        if not bass or bass not in NOTE_MAP:
            return None, f"Slash bass note '{bass}' is not recognized."

    intervals = [0, 4, 7]
    quality = "major"

    if rest.startswith(("m7b5", "min7b5", "ø")):
        intervals = [0, 3, 6, 10]
        quality = "half-diminished"
        rest = rest[4:] if rest.startswith("m7b5") else rest[6:] if rest.startswith("min7b5") else rest[1:]
    elif rest.startswith(("dim7", "°7")):
        intervals = [0, 3, 6, 9]
        quality = "diminished"
        rest = rest[4:] if rest.startswith("dim7") else rest[2:]
    elif rest.startswith(("dim", "°")):
        intervals = [0, 3, 6]
        quality = "diminished"
        rest = rest[3:] if rest.startswith("dim") else rest[1:]
    elif rest.startswith(("minor", "min")):
        intervals = [0, 3, 7]
        quality = "minor"
        rest = rest[5:] if rest.startswith("minor") else rest[3:]
    elif rest.startswith("-"):
        intervals = [0, 3, 7]
        quality = "minor"
        rest = rest[1:]
    elif rest.startswith("m") and not rest.startswith(("maj", "M")):
        intervals = [0, 3, 7]
        quality = "minor"
        rest = rest[1:]
    elif rest.startswith(("aug", "+")):
        intervals = [0, 4, 8]
        quality = "augmented"
        rest = rest[3:] if rest.startswith("aug") else rest[1:]
    elif rest.startswith("sus2"):
        intervals = [0, 2, 7]
        quality = "sus2"
        rest = rest[4:]
    elif rest.startswith(("sus4", "sus")):
        intervals = [0, 5, 7]
        quality = "sus4"
        rest = rest[4:] if rest.startswith("sus4") else rest[3:]
    elif rest.startswith("5"):
        intervals = [0, 7]
        quality = "power"
        rest = rest[1:]

    # alt means a dominant seventh with common altered tensions.
    if rest.startswith("alt"):
        intervals += [10, 13, 15, 18, 20]
        quality = "altered"
        rest = rest[3:]

    if rest.startswith(("maj11", "M11", "Δ11")):
        intervals += [11, 14, 17]
        rest = rest[5:] if rest.startswith("maj11") else rest[3:]
    elif rest.startswith(("maj13", "M13", "Δ13")):
        intervals += [11, 14, 21]
        rest = rest[5:] if rest.startswith("maj13") else rest[3:]
    elif rest.startswith(("maj9", "M9", "Δ9")):
        intervals += [11, 14]
        rest = rest[4:] if rest.startswith("maj9") else rest[2:]
    elif rest.startswith(("maj7", "M7", "Δ7")):
        intervals.append(11)
        rest = rest[4:] if rest.startswith("maj7") else rest[2:]
    elif rest.startswith("13"):
        intervals += [10, 14, 21]
        rest = rest[2:]
    elif rest.startswith("11"):
        intervals += [10, 14, 17]
        rest = rest[2:]
    elif rest.startswith("9"):
        intervals += [10, 14]
        rest = rest[1:]
    elif rest.startswith("7"):
        intervals.append(10)
        rest = rest[1:]
    elif rest.startswith("69"):
        intervals += [9, 14]
        rest = rest[2:]
    elif rest.startswith("6"):
        intervals.append(9)
        rest = rest[1:]

    # A trailing alt after 7, e.g. G7alt.
    if rest.startswith("alt"):
        intervals += [13, 15, 18, 20]
        quality = "altered"
        rest = rest[3:]

    # A sus after an extension, e.g. G7sus4, C9sus: the fourth (or second)
    # replaces the third while the seventh and tensions stay.
    if rest.startswith("sus"):
        rest = rest[3:]
        if rest.startswith("2"):
            replacement, quality = 2, "sus2"
            rest = rest[1:]
        else:
            replacement, quality = 5, "sus4"
            if rest.startswith("4"):
                rest = rest[1:]
        intervals = [i for i in intervals if i not in (3, 4)]
        intervals.append(replacement)

    # Consume every modifier; unknown degrees must not silently validate.
    while rest:
        token = re.match(r"(add[b#]?|omit|no|b|#)(13|11|9|7|6|5|4|3|2|1)(?![0-9])", rest)
        if not token:
            if rest.startswith("+"):
                intervals = [i for i in intervals if i != 7] + [8]
                rest = rest[1:]
                continue
            return None, f"Unrecognized chord text '{rest}'."
        kind, degree = token.group(1), int(token.group(2))
        base = {1: 0, 3: 4, **DEGREE_TO_INTERVAL}[degree]
        if kind in {"omit", "no"}:
            intervals = [i for i in intervals if i % 12 != base % 12
                         and not (degree == 3 and i == 3)]
        elif kind.startswith("add"):
            intervals.append(base + (1 if kind.endswith("#") else -1 if kind.endswith("b") else 0))
        else:
            intervals = [i for i in intervals if i != base]
            intervals.append(base + (-1 if kind == "b" else 1))
        rest = rest[token.end():]

    return ParsedChord(root=root, intervals=_dedupe_sorted(intervals), bass=bass, quality=quality), None


def validate_chord_symbol(symbol: str) -> tuple[bool, str | None]:
    parsed, error = parse_chord_details(symbol)
    return parsed is not None and error is None, error


def _midi_for_note(note: str, octave: int) -> int:
    return (octave + 1) * 12 + NOTE_MAP[note]


def parse_chord(symbol: str, octave: int = 4) -> list[int]:
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return []
    root_midi = _midi_for_note(parsed.root, octave)
    return sorted(set(root_midi + i for i in parsed.intervals))


def root_midi(symbol: str, octave: int = 2, prefer_slash_bass: bool = True) -> int:
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return _midi_for_note("C", octave)
    note = parsed.bass if prefer_slash_bass and parsed.bass else parsed.root
    return _midi_for_note(note, octave)


def chord_scale_notes(symbol: str, octave: int = 4) -> list[int]:
    parsed, error = parse_chord_details(symbol)
    if error or not parsed:
        return parse_chord(symbol, octave)

    root = _midi_for_note(parsed.root, octave)
    lowered_symbol = (symbol or "").lower()

    if parsed.quality == "half-diminished":
        scale = [0, 2, 3, 5, 6, 8, 10]          # Locrian
    elif parsed.quality == "diminished":
        scale = [0, 2, 3, 5, 6, 8, 9, 11]       # whole-half-ish
    elif parsed.quality == "altered" or "alt" in lowered_symbol:
        scale = [0, 1, 3, 4, 6, 8, 10]          # altered scale
    elif parsed.quality == "minor" and any(x in lowered_symbol for x in ["7", "9", "11", "13", "-"]):
        scale = [0, 2, 3, 5, 7, 9, 10]          # Dorian
    elif parsed.quality == "minor":
        scale = [0, 2, 3, 5, 7, 8, 10]          # natural minor
    elif 10 in parsed.intervals:
        scale = [0, 2, 4, 5, 7, 9, 10]          # Mixolydian
    elif 11 in parsed.intervals:
        scale = [0, 2, 4, 6, 7, 9, 11]          # Lydian for maj7 color
    else:
        scale = [0, 2, 4, 5, 7, 9, 11]

    return [root + i for i in scale]


# Ordered candidates make typo correction deterministic, preserving recognizable
# roots and slash basses. Valid symbols are always left untouched.
COMMON_SUFFIXES = ("", "m", "7", "maj7", "m7", "6", "m6", "69", "m69",
                   "9", "m9", "maj9", "11", "m11", "maj11", "13", "m13", "maj13",
                   "dim", "dim7", "m7b5", "aug", "aug7", "sus2", "sus4",
                   "7sus4", "9sus4", "13sus4", "5", "add9", "add11", "madd9",
                   "mmaj7", "mmaj9", "7alt", "7b9", "7#9", "7b5", "7#5",
                   "7b9#11", "7#9b13", "maj7#11", "13b9")


def closest_chord_symbol(symbol: str) -> str:
    if validate_chord_symbol(symbol)[0]:
        return symbol
    text = (symbol or "").strip().replace("♭", "b").replace("♯", "#")
    match = re.match(r"^([A-Ga-g][#b]?)(.*)$", text)
    if not match:
        return "C"
    root, suffix = match.groups()
    root = root[0].upper() + root[1:]
    bass = ""
    slash = re.search(r"/([A-Ga-g][#b]?)$", suffix)
    if slash:
        bass = "/" + slash[1][0].upper() + slash[1][1:]
        suffix = suffix[:slash.start()]
    suffix = _clean_suffix(suffix)
    candidate = max(COMMON_SUFFIXES, key=lambda c: SequenceMatcher(None, suffix, c).ratio())
    return root + candidate + bass
