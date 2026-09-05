"""BIAB -> MusicXML -> ChordCraft importer
Band-in-a-Box exports MusicXML with <harmony> tags. This module converts those
into ChordCraft's chord grid (measure, beat, symbol, duration).

Supports:
- <harmony> with root + kind -> chord symbol compatible with chord_parser
- Key signature from <key><fifths>
- Tempo from <sound tempo="">
- Measures and beats quantized to ChordCraft's 0 and 2 beat grid

Usage:
    project = import_musicxml_to_project(path, title=..., style=...)
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from music.groove import normalize_style, normalize_groove
from music.key_utils import normalize_key
from music.import_export import normalize_project

# MusicXML kind -> suffix mapping for ChordCraft chord_parser
KIND_MAP = {
    "major": "",
    "minor": "m",
    "augmented": "aug",
    "diminished": "dim",
    "dominant": "7",
    "major-seventh": "maj7",
    "minor-seventh": "m7",
    "diminished-seventh": "dim7",
    "augmented-seventh": "aug7",
    "half-diminished": "m7b5",
    "major-minor": "m(maj7)",
    "major-sixth": "6",
    "minor-sixth": "m6",
    "dominant-ninth": "9",
    "major-ninth": "maj9",
    "minor-ninth": "m9",
    "dominant-13th": "13",
    "major-13th": "maj13",
    "minor-13th": "m13",
    "suspended-second": "sus2",
    "suspended-fourth": "sus4",
    "power": "5",
    "dominant-11th": "11",
}

FIFTHS_TO_KEY = {
    -7: "Cb", -6: "Gb", -5: "Db", -4: "Ab", -3: "Eb", -2: "Bb", -1: "F",
    0: "C", 1: "G", 2: "D", 3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#"
}

def _root_step_to_name(step_el, alter_el) -> str:
    if step_el is None:
        return "C"
    step = (step_el.text or "C").strip()
    alter = 0
    if alter_el is not None and alter_el.text:
        try:
            alter = int(float(alter_el.text.strip()))
        except Exception:
            alter = 0
    if alter == 1:
        return step + "#"
    if alter == -1:
        return step + "b"
    if alter == 2:
        return step + "##"
    if alter == -2:
        return step + "bb"
    return step

def _kind_to_suffix(kind_text: str, degrees) -> str:
    kind = (kind_text or "major").strip().lower()
    base = KIND_MAP.get(kind, "")
    # Handle alterations like b9, #11 from degree elements
    # For now just append degrees as b#n
    extra = ""
    for deg in degrees:
        # deg is tuple (value, alter, type)
        try:
            val = int(deg.get("value", 0))
            alter = int(deg.get("alter", 0))
            dtype = deg.get("type", "add")
            if dtype == "alter":
                if alter == -1:
                    extra += f"b{val}"
                elif alter == 1:
                    extra += f"#{val}"
                else:
                    extra += f"{val}"
            elif dtype == "add":
                if alter == -1:
                    extra += f"(add b{val})"
                elif alter == 1:
                    extra += f"(add #{val})"
                else:
                    extra += f"(add {val})"
        except Exception:
            continue
    return base + extra

def import_musicxml_to_project(path: str | Path, *, title: str | None = None, style: str = "jazz", key_sig: str | None = None, groove: str = "auto") -> dict[str, Any]:
    tree = ET.parse(str(path))
    root = tree.getroot()

    # Namespace handling - MusicXML often has no namespace, but handle if present
    # Find all measures
    measures_el = root.findall(".//measure")
    if not measures_el:
        # try with namespace
        measures_el = root.findall(".//{*}measure")

    detected_tempo = None
    detected_fifths = None
    chords = []
    measure_idx = 0

    for m_el in measures_el:
        # Tempo: <sound tempo="...">
        if detected_tempo is None:
            sound_el = m_el.find("sound")
            if sound_el is None:
                sound_el = m_el.find("{*}sound")
            if sound_el is not None and sound_el.get("tempo"):
                try:
                    detected_tempo = int(float(sound_el.get("tempo")))
                except Exception:
                    pass
            # also check direction
            for dir_el in m_el.findall("direction"):
                sound_el2 = dir_el.find("sound")
                if sound_el2 is not None and sound_el2.get("tempo"):
                    try:
                        detected_tempo = int(float(sound_el2.get("tempo")))
                    except Exception:
                        pass

        # Key
        if detected_fifths is None:
            attrs = m_el.find("attributes")
            if attrs is not None:
                key_el = attrs.find("key")
                if key_el is not None:
                    fifths_el = key_el.find("fifths")
                    if fifths_el is not None and fifths_el.text:
                        try:
                            detected_fifths = int(fifths_el.text.strip())
                        except Exception:
                            pass

        # Harmonies in this measure
        # In MusicXML, harmonies can appear at different offsets, but for BIAB they are usually 2 per measure
        harmonies = m_el.findall("harmony")
        if not harmonies:
            harmonies = m_el.findall("{*}harmony")

        for h_idx, h_el in enumerate(harmonies):
            root_el = h_el.find("root")
            if root_el is None:
                root_el = h_el.find("{*}root")
                if root_el is None:
                    continue
            root_step = root_el.find("root-step")
            root_alter = root_el.find("root-alter")
            if root_step is None:
                root_step = root_el.find("{*}root-step")
                root_alter = root_el.find("{*}root-alter")
            root_name = _root_step_to_name(root_step, root_alter)

            kind_el = h_el.find("kind")
            if kind_el is None:
                kind_el = h_el.find("{*}kind")
            kind_text = kind_el.text if kind_el is not None and kind_el.text else "major"

            # degree alterations
            degree_els = h_el.findall("degree")
            degrees = []
            for d_el in degree_els:
                d_val = d_el.find("degree-value")
                d_alter = d_el.find("degree-alter")
                d_type = d_el.find("degree-type")
                degrees.append({
                    "value": d_val.text if d_val is not None else "0",
                    "alter": d_alter.text if d_alter is not None else "0",
                    "type": d_type.text if d_type is not None else "add"
                })

            suffix = _kind_to_suffix(kind_text, degrees)
            symbol = root_name + suffix

            # Quantize beat: first harmony = beat 0, second = beat 2, etc.
            beat = 0 if h_idx == 0 else 2
            # If explicit offset, could refine, but BIAB usually 0,2

            chords.append({
                "measure": measure_idx,
                "beat": beat,
                "symbol": symbol,
                "duration": 2.0 if beat == 2 else 4.0
            })

        measure_idx += 1

    # Resolve key
    if key_sig is None:
        if detected_fifths is not None and detected_fifths in FIFTHS_TO_KEY:
            key_sig = FIFTHS_TO_KEY[detected_fifths]
        else:
            key_sig = "C"
    key_sig = normalize_key(key_sig)
    tempo = detected_tempo or 120
    title = title or Path(path).stem

    style = normalize_style(style)
    groove = normalize_groove(groove, style)

    return normalize_project({
        "song": {
            "title": title,
            "tempo": tempo,
            "key_sig": key_sig,
            "style": style,
            "groove": groove,
            "measures": max(12, measure_idx),
            "choruses": 1
        },
        "chords": chords
    })
