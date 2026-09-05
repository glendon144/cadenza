"""Import/export helpers for ChordCraft project files and simple MIDI chord grids."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pretty_midi

from music.chord_parser import note_name_for_pc
from music.groove import normalize_style, normalize_groove
from music.key_utils import normalize_key

FORMAT_NAME = "chordcraft.song"
FORMAT_VERSION = 3


def _safe_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def normalize_project(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize ChordCraft's JSON interchange format.

    The format is intentionally small and human-readable so a tune can be saved
    to disk, edited later, or shared without the SQLite database.
    """
    if "song" in data:
        song = data.get("song") or {}
        chords = data.get("chords") or []
    else:
        song = data
        chords = data.get("chords") or []

    style = normalize_style(song.get("style", "jazz"))
    groove = normalize_groove(song.get("groove", "auto"), style)
    key_sig = normalize_key(song.get("key_sig", song.get("key", "C")))
    measures = _safe_int(song.get("measures", data.get("measures", 12)), 12, 1, 240)
    choruses = _safe_int(song.get("choruses", data.get("choruses", 1)), 1, 1, 20)
    tempo = _safe_int(song.get("tempo", 120), 120, 30, 360)
    melodic_temperature = _safe_int(song.get("melodic_temperature", data.get("melodic_temperature", 35)), 35, 0, 100)
    rms_phrasing = bool(song.get("rms_phrasing", data.get("rms_phrasing", False)))

    clean_chords: list[dict[str, Any]] = []
    max_measure = measures - 1
    for raw in chords:
        try:
            measure = int(raw.get("measure", 0))
            beat = int(raw.get("beat", 0))
        except (TypeError, ValueError):
            continue
        if beat not in (0, 2):
            beat = 0 if beat < 2 else 2
        symbol = str(raw.get("symbol", "")).strip()
        if not symbol:
            continue
        duration = float(raw.get("duration", 2.0 if beat == 2 else 4.0))
        if measure < 0:
            continue
        max_measure = max(max_measure, measure)
        clean_chords.append({
            "measure": measure,
            "beat": beat,
            "symbol": symbol[:40],
            "duration": max(0.25, min(16.0, duration)),
        })

    measures = max(measures, max_measure + 1)
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "song": {
            "title": str(song.get("title", "Untitled") or "Untitled")[:120],
            "tempo": tempo,
            "key_sig": key_sig,
            "style": style,
            "groove": groove,
            "measures": measures,
            "choruses": choruses,
            "scale_focus": bool(song.get("scale_focus", False)),
            "melodic_temperature": melodic_temperature,
            "rms_phrasing": rms_phrasing,
        },
        "chords": sorted(clean_chords, key=lambda c: (c["measure"], c["beat"])),
    }


def dumps_project(song: dict[str, Any], chords: list[dict[str, Any]], *, measures: int | None = None, choruses: int = 1, scale_focus: bool = False, melodic_temperature: int = 35, rms_phrasing: bool = False) -> str:
    payload = normalize_project({
        "song": {
            "title": song.get("title", "Untitled"),
            "tempo": song.get("tempo", 120),
            "key_sig": song.get("key_sig", "C"),
            "style": song.get("style", "jazz"),
            "groove": song.get("groove", "auto"),
            "measures": measures or (max((int(c.get("measure", 0)) for c in chords), default=11) + 1),
            "choruses": choruses,
            "scale_focus": scale_focus,
            "melodic_temperature": melodic_temperature,
            "rms_phrasing": rms_phrasing,
        },
        "chords": chords,
    })
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def loads_project(text: str) -> dict[str, Any]:
    return normalize_project(json.loads(text))


QUALITY_NAMES = {
    (0, 4, 7, 11): "maj7",
    (0, 4, 7, 10): "7",
    (0, 3, 7, 10): "m7",
    (0, 3, 6, 10): "m7b5",
    (0, 3, 6, 9): "dim7",
    (0, 4, 7): "",
    (0, 3, 7): "m",
    (0, 3, 6): "dim",
}


def _infer_chord_symbol(pcs: set[int], prefer_flats: bool = True) -> str | None:
    if not pcs:
        return None
    best: tuple[int, int, int, str] | None = None
    for root in range(12):
        intervals = tuple(sorted((p - root) % 12 for p in pcs))
        # Compare against common jazz chord types and prefer complete matches;
        # this is intentionally conservative rather than pretending to know a
        # full harmonic analysis from arbitrary MIDI.
        for quality_intervals, suffix in QUALITY_NAMES.items():
            qset = set(quality_intervals)
            covered = len(set(intervals) & qset)
            extras = len(set(intervals) - qset)
            missing_root = 0 if 0 in intervals else 1
            score = covered * 10 - extras * 4 - missing_root * 3
            if covered >= 2:
                symbol = note_name_for_pc(root, prefer_flats=prefer_flats) + suffix
                candidate = (score, covered, -extras, symbol)
                if best is None or candidate > best:
                    best = candidate
    return best[3] if best else note_name_for_pc(next(iter(pcs)), prefer_flats=prefer_flats)


def import_midi_to_project(path: str | Path, *, title: str | None = None, style: str = "jazz", key_sig: str = "C") -> dict[str, Any]:
    """Import MIDI into ChordCraft's grid by quantizing notes to beats 1 and 3.

    The app's grid stores chords, not arbitrary performed tracks.  For import we
    therefore keep the first useful pitched material, drop drum channels, quantize
    note starts to half-bar cells, and infer compact chord symbols from note
    clusters.  It is a practical sketch import, not a full transcription engine.
    """
    midi = pretty_midi.PrettyMIDI(str(path))
    tempo = int(round(midi.estimate_tempo() or 120))
    key_sig = normalize_key(key_sig)
    prefer_flats = key_sig in {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
    notes = []
    for inst in midi.instruments:
        if inst.is_drum:
            continue
        for note in inst.notes:
            notes.append(note)
    if not notes:
        return normalize_project({"song": {"title": title or Path(path).stem, "tempo": tempo, "key_sig": key_sig, "style": style, "measures": 12}, "chords": []})

    bps = tempo / 60.0
    max_beat = max(n.end * bps for n in notes)
    measures = max(1, int(max_beat // 4) + 1)
    buckets: dict[tuple[int, int], set[int]] = {}
    for note in notes:
        beat_float = note.start * bps
        measure = max(0, int(beat_float // 4))
        beat_in_measure = beat_float - measure * 4
        beat = 0 if beat_in_measure < 2.0 else 2
        buckets.setdefault((measure, beat), set()).add(note.pitch % 12)

    chords = []
    for (measure, beat), pcs in sorted(buckets.items()):
        symbol = _infer_chord_symbol(pcs, prefer_flats=prefer_flats)
        if symbol:
            chords.append({"measure": measure, "beat": beat, "symbol": symbol, "duration": 2.0 if beat == 2 else 4.0})
    return normalize_project({
        "song": {"title": title or Path(path).stem, "tempo": tempo, "key_sig": key_sig, "style": style, "groove": "auto", "measures": measures, "choruses": 1},
        "chords": chords,
    })
