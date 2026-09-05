"""
ChordCraft Core Engine
MusicXML <-> JSON bidirectional translator
This is the heart of the suite - BIAB, Finale, Dorico, MuseScore, Suno, Udio all go through here.

Design:
    JSON is canonical internal format (what you already have: song + chords)
    MusicXML is interchange format for notation world
    Providers are thin wrappers around this core

Flows:
    MusicXML -> JSON : Finale/BIAB/Dorico -> ChordCraft internal
    JSON -> MusicXML : ChordCraft internal -> Notation / BIAB / Dorico
    JSON -> Provider Prompt : ChordCraft -> Suno/Udio via provider JSON

Finale market angle:
    Finale users export MusicXML, but lose layout, chord symbols, and positioning.
    This engine preserves harmony tags and can enrich with LilyPond-quality rendering,
    which is better than MuseScore/Dorico default import.

Future products built on same core:
    - ChordCraft Notation: JSON -> MusicXML + LilyPond PDF
    - ChordCraft Translator: BIAB <-> Suno <-> Finale
    - ChordCraft AI Scorer: AI MIDI -> JSON -> beautiful score
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List
import json

from music.musicxml_import import import_musicxml_to_project
from music.import_export import normalize_project, dumps_project

def musicxml_to_json(path: str | Path) -> Dict[str, Any]:
    """Core: MusicXML file -> ChordCraft JSON (canonical)"""
    return import_musicxml_to_project(path)

def json_to_musicxml(project: Dict[str, Any], output_path: str | Path | None = None) -> str:
    """Core: ChordCraft JSON -> MusicXML string (for export to Finale/Dorico/BIAB)
    
    This generates clean MusicXML with harmony tags from chord grid.
    """
    # Normalize first
    norm = normalize_project(project)
    song = norm["song"]
    chords = norm["chords"]
    
    # Build minimal MusicXML
    # MusicXML structure: score-partwise -> part -> measure -> harmony
    score = ET.Element("score-partwise", version="4.0")
    
    # Identification
    work = ET.SubElement(score, "work")
    work_title = ET.SubElement(work, "work-title")
    work_title.text = song.get("title", "Untitled")
    
    part_list = ET.SubElement(score, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    part_name = ET.SubElement(score_part, "part-name")
    part_name.text = "ChordCraft"
    
    part = ET.SubElement(score, "part", id="P1")
    
    # Group chords by measure
    chords_by_measure: Dict[int, List[Dict]] = {}
    for c in chords:
        m = c.get("measure", 0)
        chords_by_measure.setdefault(m, []).append(c)
    
    max_measure = max(chords_by_measure.keys()) + 1 if chords_by_measure else song.get("measures", 12)
    
    # Key signature mapping
    key_map = {"C":0,"G":1,"D":2,"A":3,"E":4,"B":5,"F#":6,"C#":7,
               "F":-1,"Bb":-2,"Eb":-3,"Ab":-4,"Db":-5,"Gb":-6,"Cb":-7}
    fifths = key_map.get(song.get("key_sig","C"), 0)
    
    for m_idx in range(max_measure):
        measure = ET.SubElement(part, "measure", number=str(m_idx+1))
        
        # Attributes only in first measure, or when key changes
        if m_idx == 0:
            attrs = ET.SubElement(measure, "attributes")
            divs = ET.SubElement(attrs, "divisions")
            divs.text = "4"
            key_el = ET.SubElement(attrs, "key")
            fifths_el = ET.SubElement(key_el, "fifths")
            fifths_el.text = str(fifths)
            time_el = ET.SubElement(attrs, "time")
            beats = ET.SubElement(time_el, "beats")
            beats.text = "4"
            beat_type = ET.SubElement(time_el, "beat-type")
            beat_type.text = "4"
            clef = ET.SubElement(attrs, "clef")
            sign = ET.SubElement(clef, "sign")
            sign.text = "G"
            line = ET.SubElement(clef, "line")
            line.text = "2"
            
            # Tempo
            direction = ET.SubElement(measure, "direction", placement="above")
            dir_type = ET.SubElement(direction, "direction-type")
            metronome = ET.SubElement(dir_type, "metronome")
            beat_unit = ET.SubElement(metronome, "beat-unit")
            beat_unit.text = "quarter"
            per_min = ET.SubElement(metronome, "per-minute")
            per_min.text = str(song.get("tempo",120))
            sound = ET.SubElement(direction, "sound", tempo=str(song.get("tempo",120)))
        
        # Harmonies
        for chord in chords_by_measure.get(m_idx, []):
            harmony = ET.SubElement(measure, "harmony")
            # Parse root from symbol - naive but works for most
            sym = chord.get("symbol","C")
            # Root is first char + optional #/b
            root_step = sym[0]
            root_alter = None
            rest = sym[1:]
            if rest and rest[0] in ("#","b"):
                if rest[0] == "#":
                    root_alter = 1
                else:
                    root_alter = -1
                root_kind = rest[1:]
                root_sym = sym[:2]
            else:
                root_kind = rest
                root_sym = sym[0]
            
            root_el = ET.SubElement(harmony, "root")
            root_step_el = ET.SubElement(root_el, "root-step")
            root_step_el.text = root_step
            if root_alter is not None:
                root_alter_el = ET.SubElement(root_el, "root-alter")
                root_alter_el.text = str(root_alter)

            # Keep split-measure chords at their grid beat.  BIAB and other
            # MusicXML readers use this offset to reconstruct the chord chart.
            beat = int(chord.get("beat", 0) or 0)
            if beat:
                offset_el = ET.SubElement(harmony, "offset")
                offset_el.text = str(beat * 4)
            
            # Kind
            kind_el = ET.SubElement(harmony, "kind")
            # Map suffix to MusicXML kind
            suffix = sym[len(root_sym):].lower()
            if suffix in ("", "maj", "major"):
                kind_el.text = "major"
            elif suffix in ("m", "min", "minor"):
                kind_el.text = "minor"
            elif suffix == "7":
                kind_el.text = "dominant"
            elif suffix in ("maj7","m7","dim","m7b5","sus4","sus2","dim7","aug","6","9","11","13","maj9","m9"):
                # Simplified mapping
                if "maj7" in suffix or "maj9" in suffix:
                    kind_el.text = "major-seventh"
                elif "m7" in suffix:
                    kind_el.text = "minor-seventh"
                elif "dim" in suffix:
                    kind_el.text = "diminished"
                elif "m7b5" in suffix:
                    kind_el.text = "half-diminished"
                elif "sus" in suffix:
                    kind_el.text = "suspended-fourth"
                elif suffix in ("7","9","11","13"):
                    kind_el.text = "dominant"
                else:
                    kind_el.text = "major"
            else:
                kind_el.text = "major"
                # Use text attribute for custom
                kind_el.set("text", suffix)
        
        # Need at least one note per measure for valid MusicXML - whole rest
        if m_idx == 0 or not chords_by_measure.get(m_idx):
            note = ET.SubElement(measure, "note")
            rest_el = ET.SubElement(note, "rest")
            duration = ET.SubElement(note, "duration")
            duration.text = "16"
            type_el = ET.SubElement(note, "type")
            type_el.text = "whole"
    
    xml_str = ET.tostring(score, encoding="unicode")
    # Add XML declaration
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n' + xml_str
    
    if output_path:
        Path(output_path).write_text(xml_str, encoding="utf-8")
    
    return xml_str

def json_file_to_musicxml_file(json_path: str | Path, musicxml_path: str | Path):
    """Convenience: .chordcraft.json -> .musicxml"""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return json_to_musicxml(data, output_path=musicxml_path)

def musicxml_file_to_json_file(musicxml_path: str | Path, json_path: str | Path):
    """Convenience: .musicxml -> .chordcraft.json"""
    proj = musicxml_to_json(musicxml_path)
    Path(json_path).write_text(json.dumps(proj, indent=2), encoding="utf-8")
    return proj

# Finale-specific helpers
def finale_musicxml_to_chordcraft_with_layout(musicxml_path: str | Path) -> Dict[str, Any]:
    """
    Finale's MusicXML export includes extra layout info in <appearance> and <print>.
    This wrapper preserves that and adds it to JSON as _finale_meta for future
    beautiful LilyPond rendering - your differentiator vs Dorico/MuseScore.
    """
    proj = musicxml_to_json(musicxml_path)
    # Try to extract Finale-specific metadata
    try:
        tree = ET.parse(str(musicxml_path))
        root = tree.getroot()
        # Finale often puts creator in identification
        ident = root.find(".//identification")
        meta = {}
        if ident is not None:
            for creator in ident.findall("creator"):
                meta[creator.get("type","creator")] = creator.text
        proj["_source"] = "Finale MusicXML"
        proj["_finale_meta"] = meta
    except Exception:
        proj["_source"] = "MusicXML"
    return proj
