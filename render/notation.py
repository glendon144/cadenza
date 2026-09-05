"""Render ChordCraft arrangements to LilyPond SVG/PDF notation."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
import pretty_midi
from config import LILYPOND_BIN, EXPORT_DIR
from music.key_utils import lilypond_key_name, lilypond_note_name_for_pc, transpose_chord_symbol, transposed_key_sig
from render.preflight import require_dependencies


def midi_note_to_ly(midi: int, key_sig: str = "C") -> str:
    pc = midi % 12
    oct_ = midi // 12 - 1
    name = lilypond_note_name_for_pc(pc, key_sig)
    if oct_ >= 4:
        name += "'" * (oct_ - 3)
    elif oct_ < 3:
        name += "," * (3 - oct_)
    return name


def ly_duration(beats: float) -> str:
    """Return a LilyPond duration for quarter-note beat units.

    ChordCraft stores time in beats where 1.0 means a quarter note.
    LilyPond durations are reciprocal note values, so the mapping must be
    exact: 0.5 beat -> eighth note, 0.75 beat -> dotted eighth,
    1.5 beats -> dotted quarter, and so on.  The previous approximation
    rounded 0.75 to a quarter and 1.5 to a half note, which made bossa
    comping bars display with too many beats.
    """
    beats = round(float(beats) * 4) / 4
    mapping = {
        4.0: "1",
        3.0: "2.",
        2.0: "2",
        1.5: "4.",
        1.0: "4",
        0.75: "8.",
        0.5: "8",
        0.25: "16",
    }
    return mapping.get(beats, "16")


def quantize_start(beats: float) -> float:
    return max(0.0, round(float(beats) * 4) / 4)


def quantize_duration(beats: float) -> float:
    return max(0.25, math.ceil(float(beats) * 4 - 0.001) / 4)


def rest_tokens(beats: float) -> list[str]:
    tokens: list[str] = []
    remaining = quantize_duration(beats)
    for dur in (4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.25):
        while remaining >= dur - 0.001:
            tokens.append(f"r{ly_duration(dur)}")
            remaining = round(remaining - dur, 4)
    return tokens



DRUM_LY_NAMES = {
    36: "bd",
    37: "sidestick",
    38: "sn",
    42: "hh",
    44: "hhp",
    45: "toml",
    46: "hho",
    47: "tommh",
    49: "cymc",
    50: "tomh",
    51: "cymr",
}


def _format_drums(pitches: list[int], duration: str) -> str:
    names = [DRUM_LY_NAMES.get(int(p), "sn") for p in sorted(set(pitches))]
    if len(names) == 1:
        return f"{names[0]}{duration}"
    return f"<{' '.join(names)}>{duration}"


def events_to_ly_drum_voice(events: list[dict], total_beats: float, tempo: int) -> str:
    # Convert drum events to LilyPond drummode notation.
    if not events:
        return " ".join(rest_tokens(total_beats))
    # Use one compact hit duration per attack point so kick/snare/cymbal
    # combinations print as one stacked drum chord instead of colliding voices.
    groups: dict[float, list[int]] = {}
    for evt in events:
        start = quantize_start(evt["start"])
        if 0 <= start < total_beats - 0.001:
            groups.setdefault(start, []).append(int(evt["pitch"]))
    items = []
    for start, pitches in groups.items():
        duration = 0.25
        items.append({"start": start, "duration": duration, "ly": _format_drums(pitches, ly_duration(duration))})
    items.sort(key=lambda e: e["start"])
    lines: list[str] = []
    cursor = 0.0
    for item in items:
        start = float(item["start"])
        end = start + float(item["duration"])
        if start < cursor - 0.001:
            # Avoid overlapping hits in the single printed drum voice. The MIDI
            # playback still contains the original kit texture.
            continue
        gap = start - cursor
        if gap >= 0.25:
            lines.extend(rest_tokens(gap))
        lines.append(item["ly"])
        cursor = max(cursor, end)
    remaining = total_beats - cursor
    if remaining >= 0.25:
        lines.extend(rest_tokens(remaining))
    return " ".join(lines)

def event_segments(evt: dict, total_beats: float, beats_per_measure: float = 4.0) -> list[tuple[float, float, int]]:
    """Quantize one MIDI note and split notation at barlines.

    MIDI playback notes are often shortened for articulation.  Notation needs
    regular rhythmic slots, but a rounded-up note that begins late in a bar can
    otherwise spill over the barline and make LilyPond show 4 1/2 beats in one
    measure and too few in the next.  Splitting at measure boundaries keeps each
    rendered bar honest.
    """
    start = quantize_start(evt["start"])
    duration = quantize_duration(evt["duration"])
    end = min(float(total_beats), start + duration)
    pitch = int(evt["pitch"])
    segments: list[tuple[float, float, int]] = []
    while start < end - 0.001:
        bar_end = (math.floor(start / beats_per_measure) + 1) * beats_per_measure
        seg_end = min(end, bar_end)
        seg_dur = round(seg_end - start, 4)
        if seg_dur >= 0.25 - 0.001:
            segments.append((round(start, 4), quantize_duration(seg_dur), pitch))
        start = seg_end
    return segments


def _format_pitches(pitches: list[int], duration: str, key_sig: str) -> str:
    names = [midi_note_to_ly(p, key_sig) for p in sorted(set(pitches))]
    return f"{names[0]}{duration}" if len(names) == 1 else f"<{' '.join(names)}>{duration}"


def tied_note_tokens(pitches: list[int], beats: float, key_sig: str) -> list[str]:
    """Render a duration as one printable note, or several tied notes.

    Quarter-multiple durations such as 2.5 or 1.25 beats have no single
    LilyPond note value.  Decompose them the same way rest_tokens splits
    rests, tying the pieces so playback length is preserved on paper.
    """
    remaining = quantize_duration(beats)
    parts: list[str] = []
    for dur in (4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.25):
        while remaining >= dur - 0.001:
            parts.append(ly_duration(dur))
            remaining = round(remaining - dur, 4)
    if not parts:
        parts = [ly_duration(0.25)]
    return [
        _format_pitches(pitches, dur_str, key_sig) + ("~" if i + 1 < len(parts) else "")
        for i, dur_str in enumerate(parts)
    ]


def _triplet_items(events: list[dict], key_sig: str) -> tuple[list[dict], set[int]]:
    """Collapse explicit triplet events into LilyPond tuplet items.

    Melody events mark a complete triplet group even when one or two slots are
    rests.  That lets notation finish the triplet once it has started, instead
    of rounding 1/3-beat notes into ordinary sixteenths.
    """
    by_group: dict[str, list[dict]] = {}
    consumed: set[int] = set()
    for idx, evt in enumerate(events):
        gid = evt.get("tuplet_group")
        if evt.get("tuplet") == "triplet" and gid:
            by_group.setdefault(str(gid), []).append(evt)
            consumed.add(idx)

    items: list[dict] = []
    for gid, group_events in by_group.items():
        first = group_events[0]
        unit = float(first.get("tuplet_unit", 1.0 / 3.0))
        group_start = float(first.get("tuplet_start", min(e["start"] for e in group_events)))
        written_duration = "8" if unit < 0.5 else "4"
        slots: list[list[int]] = [[], [], []]
        for evt in group_events:
            slot = int(evt.get("tuplet_slot", round((float(evt["start"]) - group_start) / unit)))
            if 0 <= slot < 3:
                slots[slot].append(int(evt["pitch"]))
        tokens = []
        for slot_pitches in slots:
            if slot_pitches:
                tokens.append(_format_pitches(slot_pitches, written_duration, key_sig))
            else:
                tokens.append(f"r{written_duration}")
        items.append({
            "start": round(group_start, 6),
            "duration": round(unit * 3.0, 6),
            "ly": "\\tuplet 3/2 { " + " ".join(tokens) + " }",
        })
    return items, consumed


def events_to_ly_voice(events: list[dict], total_beats: float, tempo: int, key_sig: str = "C") -> str:
    if not events:
        return " ".join(rest_tokens(total_beats))

    triplet_render_items, consumed_indexes = _triplet_items(events, key_sig)

    groups: dict[tuple[float, float], list[int]] = {}
    for idx, evt in enumerate(events):
        if idx in consumed_indexes:
            continue
        for start, duration, pitch in event_segments(evt, total_beats):
            key = (start, duration)
            groups.setdefault(key, []).append(pitch)

    items = list(triplet_render_items)
    for (start, duration), pitches in groups.items():
        items.append({
            "start": start,
            "duration": duration,
            "pitches": sorted(set(pitches)),
        })
    items.sort(key=lambda e: e["start"])

    lines: list[str] = []
    cursor = 0.0
    for item in items:
        start = float(item["start"])
        end = start + float(item["duration"])
        if start < cursor - 0.001:
            if end <= cursor + 0.001:
                continue
            # Avoid overlapping notation in a single voice.  Tuplet groups are
            # left intact; ordinary events are trimmed to start at the cursor.
            if "pitches" not in item:
                continue
            start = cursor
            item["duration"] = quantize_duration(end - cursor)
        gap = start - cursor
        if gap >= 0.25:
            lines.extend(rest_tokens(gap))
        if "pitches" in item:
            lines.extend(tied_note_tokens(item["pitches"], float(item["duration"]), key_sig))
        else:
            lines.append(item["ly"])
        cursor = max(cursor, start + float(item["duration"]))

    remaining = total_beats - cursor
    if remaining >= 0.25:
        lines.extend(rest_tokens(remaining))
    return " ".join(lines)

def escape_ly_markup(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def chord_symbols_to_ly(chord_cells: list[dict] | None, total_beats: float) -> str:
    """Return LilyPond spacer notes carrying chord-symbol markup.

    Multiple chord cells in the same 4/4 measure are rendered as half-measure
    skips, so beat 0 + beat 2 becomes two chord symbols in one bar.
    """
    total_measures = int(math.ceil(total_beats / 4.0))

    if not chord_cells:
        return " ".join("s1" for _ in range(total_measures))

    cells_by_measure: dict[int, list[dict]] = {}

    for cell in chord_cells:
        symbol = str(cell.get("symbol", "")).strip()
        if not symbol:
            continue

        measure = int(cell.get("measure", 0))
        beat = float(cell.get("beat", 0))
        duration = float(cell.get("duration", 0) or 0)

        cells_by_measure.setdefault(measure, []).append({
            "beat": beat,
            "duration": duration,
            "symbol": symbol,
        })

    if cells_by_measure:
        total_measures = max(total_measures, max(cells_by_measure) + 1)

    tokens: list[str] = []

    for measure in range(total_measures):
        cells = sorted(cells_by_measure.get(measure, []), key=lambda c: c["beat"])

        if not cells:
            tokens.append("s1")
            continue

        if len(cells) >= 2:
            for cell in cells:
                symbol = escape_ly_markup(cell["symbol"])
                tokens.append(f's2^\\markup \\bold "{symbol}"')
            continue

        cell = cells[0]
        symbol = escape_ly_markup(cell["symbol"])
        beat = cell["beat"]
        duration = cell["duration"]

        if beat >= 2:
            tokens.append("s2")
            tokens.append(f's2^\\markup \\bold "{symbol}"')
        elif duration and duration <= 2:
            tokens.append(f's2^\\markup \\bold "{symbol}"')
        else:
            tokens.append(f's1^\\markup \\bold "{symbol}"')

    return " ".join(tokens)

def _midi_note_to_event(note, tempo: int) -> dict:
    bps = tempo / 60.0
    return {"pitch": note.pitch, "start": note.start * bps, "duration": (note.end - note.start) * bps, "velocity": note.velocity}


def _events_from_instrument(instrument, tempo: int) -> list[dict]:
    return [_midi_note_to_event(note, tempo) for note in instrument.notes]


def _build_lilypond_source(
    chord_events: list[dict],
    bass_events: list[dict],
    solo_events: list[dict],
    drum_events: list[dict],
    total_beats: float,
    tempo: int,
    title: str = "ChordCraft",
    chord_cells: list[dict] | None = None,
    key_sig: str = "C",
    view: str = "full",
    transposition: int = 0,
    transposition_label: str | None = None,
) -> str:
    if transposition:
        # Written-pitch view for a transposing instrument: shift every pitched
        # staff, the key signature, and the chord symbols. Playback (MIDI and
        # audio) stays at concert pitch; only the notation changes. Drums are
        # unpitched and stay put.
        written_key = transposed_key_sig(key_sig, transposition)

        def _shift(events: list[dict]) -> list[dict]:
            return [{**e, "pitch": int(e["pitch"]) + transposition} for e in events]

        chord_events = _shift(chord_events)
        bass_events = _shift(bass_events)
        solo_events = _shift(solo_events)
        if chord_cells:
            chord_cells = [
                {**c, "symbol": transpose_chord_symbol(str(c.get("symbol", "")), transposition, written_key)}
                for c in chord_cells
            ]
        key_sig = written_key

    chord_right_events = [e for e in chord_events if int(e.get("pitch", 0)) >= 60]
    chord_left_events = [e for e in chord_events if int(e.get("pitch", 0)) < 60]
    total_beats = max(4.0, math.ceil(float(total_beats) / 4.0) * 4.0)

    right_voice = events_to_ly_voice(solo_events, total_beats, tempo, key_sig)
    chord_symbol_voice = chord_symbols_to_ly(chord_cells, total_beats)
    chord_right_voice = events_to_ly_voice(chord_right_events, total_beats, tempo, key_sig)
    chord_left_voice = events_to_ly_voice(chord_left_events, total_beats, tempo, key_sig)
    left_voice = events_to_ly_voice(bass_events, total_beats, tempo, key_sig)
    drum_voice = events_to_ly_drum_voice(drum_events, total_beats, tempo)
    ly_key = lilypond_key_name(key_sig)

    view = (view or "full").lower()
    if view not in {"full", "solo", "bass", "rhythm", "drums"}:
        view = "full"

    safe_title = escape_ly_markup(title)
    view_subtitle = {
        "full": "Full Score",
        "solo": "Solo Part",
        "bass": "Bass Part",
        "rhythm": "Rhythm Part",
        "drums": "Drum Part",
    }[view]
    if transposition and transposition_label:
        view_subtitle = f"{view_subtitle} — Written for {escape_ly_markup(transposition_label)}"

    definitions = rf'''
\version "2.24.0"

\header {{
  title = "{safe_title}"
  subtitle = "{view_subtitle}"
  composer = "ChordCraft"
  tagline = ##f
}}

upper = {{
  \clef treble
  \tempo 4 = {int(tempo)}
  \time 4/4
  \key {ly_key} \major
  <<
    {{ {chord_symbol_voice} }}
    {{ {right_voice} }}
  >>
  \bar "|."
}}

soloOnly = {{
  \clef treble
  \tempo 4 = {int(tempo)}
  \time 4/4
  \key {ly_key} \major
  <<
    {{ {chord_symbol_voice} }}
    {{ {right_voice} }}
  >>
  \bar "|."
}}

bassOnly = {{
  \clef bass
  \tempo 4 = {int(tempo)}
  \time 4/4
  \key {ly_key} \major
  <<
    {{ {chord_symbol_voice} }}
    {{ {left_voice} }}
  >>
  \bar "|."
}}

rhythmUpper = {{
  \clef treble
  \tempo 4 = {int(tempo)}
  \time 4/4
  \key {ly_key} \major
  <<
    {{ {chord_symbol_voice} }}
    {{ {chord_right_voice} }}
  >>
  \bar "|."
}}

chordRight = {{
  \clef treble
  \time 4/4
  \key {ly_key} \major
  {chord_right_voice}
  \bar "|."
}}

chordLeft = {{
  \clef bass
  \time 4/4
  \key {ly_key} \major
  {chord_left_voice}
  \bar "|."
}}

lower = {{
  \clef bass
  \time 4/4
  \key {ly_key} \major
  {left_voice}
  \bar "|."
}}

drumPart = \drummode {{
  \tempo 4 = {int(tempo)}
  \time 4/4
  {drum_voice}
  \bar "|."
}}

'''

    score_blocks = {
        "solo": r'''
\score {
  \new Staff \with { instrumentName = "Solo" } \soloOnly
  \layout { }
  \midi { }
}
''',
        "bass": r'''
\score {
  \new Staff \with { instrumentName = "Bass" } \bassOnly
  \layout { }
  \midi { }
}
''',
        "rhythm": r'''
\score {
  \new PianoStaff \with { instrumentName = "Rhythm" } <<
    \new Staff = "rhythmUpper" \rhythmUpper
    \new Staff = "chordLeft" \chordLeft
  >>
  \layout { }
  \midi { }
}
''',
        "drums": r'''
\score {
  \new DrumStaff \with { instrumentName = "Drums" } \drumPart
  \layout { }
  \midi { }
}
''',
        "full": r'''
\score {
  \new StaffGroup <<
    \new Staff = "upper" \with { instrumentName = "Solo" } \upper
    \new PianoStaff \with { instrumentName = "Piano" } <<
      \new Staff = "chordRight" \chordRight
      \new Staff = "chordLeft" \chordLeft
      \new Staff = "lower" \lower
    >>
    \new DrumStaff \with { instrumentName = "Drums" } \drumPart
  >>
  \layout { }
  \midi { }
}
''',
    }
    return definitions + score_blocks[view]


def build_lilypond_source_from_arrangement(arrangement: dict, tempo: int, title: str = "ChordCraft", chord_cells: list[dict] | None = None, key_sig: str = "C", view: str = "full", transposition: int = 0, transposition_label: str | None = None) -> str:
    """Build LilyPond directly from beat-based arrangement events.

    This preserves triplet metadata and avoids re-inferring musical notation from
    MIDI playback durations, which are intentionally shortened for articulation.
    """
    return _build_lilypond_source(
        arrangement.get("chord_events", []),
        arrangement.get("bass_events", []),
        arrangement.get("solo_events", []),
        arrangement.get("drum_events", []),
        arrangement.get("total_beats", 16.0),
        tempo,
        title=title,
        chord_cells=chord_cells,
        key_sig=key_sig,
        view=view,
        transposition=transposition,
        transposition_label=transposition_label,
    )


def build_lilypond_source_from_midi(midi_path: str | Path, tempo: int, title: str = "ChordCraft", chord_cells: list[dict] | None = None, key_sig: str = "C", view: str = "full") -> str:
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    instruments = midi.instruments
    chord_track = instruments[0] if len(instruments) > 0 else None
    bass_track = instruments[1] if len(instruments) > 1 else None
    solo_track = instruments[2] if len(instruments) > 2 else None
    drum_track = instruments[3] if len(instruments) > 3 else None

    chord_events = _events_from_instrument(chord_track, tempo) if chord_track else []
    bass_events = _events_from_instrument(bass_track, tempo) if bass_track else []
    solo_events = _events_from_instrument(solo_track, tempo) if solo_track else []
    drum_events = _events_from_instrument(drum_track, tempo) if drum_track else []
    all_events = chord_events + bass_events + solo_events + drum_events
    max_end = max((e["start"] + e["duration"] for e in all_events), default=16.0)
    total_beats = max(4.0, math.ceil(max_end / 4.0) * 4.0)
    return _build_lilypond_source(chord_events, bass_events, solo_events, drum_events, total_beats, tempo, title, chord_cells, key_sig, view=view)

def _render_lilypond(ly_source: str, output_stem: str, svg: bool, output_dir: str | Path | None = None) -> Path:
    require_dependencies(include_lilypond=True, include_audio=False)
    output_dir = Path(output_dir or EXPORT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ly_path = output_dir / f"{output_stem}.ly"
    ly_path.write_text(ly_source, encoding="utf-8")
    cmd = [LILYPOND_BIN]
    if svg:
        cmd.append("--svg")
    cmd.extend(["-o", str(output_dir / output_stem), str(ly_path)])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(output_dir))
    if result.returncode != 0:
        raise RuntimeError(f"LilyPond error:\n{result.stderr}")
    return output_dir


def collect_svg_pages(output_dir: str | Path, output_stem: str = "score") -> list[str]:
    """Return every SVG page LilyPond produced, in page order.

    LilyPond emits one SVG file per page for scores that wrap onto more
    than one page, usually as ``score-1.svg``, ``score-2.svg``, etc.  The
    older ChordCraft front-end only displayed the first file, which made a
    longer chart look truncated even though the MIDI/audio contained the full
    song.
    """
    output_dir = Path(output_dir)
    single_page = output_dir / f"{output_stem}.svg"

    def page_number(path: Path) -> int:
        stem = path.stem
        if stem == output_stem:
            return 1
        suffix = stem.removeprefix(f"{output_stem}-")
        return int(suffix) if suffix.isdigit() else 999999

    numbered_pages = sorted(
        output_dir.glob(f"{output_stem}-*.svg"),
        key=page_number,
    )
    pages = numbered_pages or ([single_page] if single_page.exists() else [])
    return [str(path) for path in pages if path.exists()]


def render_svgs(ly_source: str, output_stem: str = "score", output_dir: str | Path | None = None) -> list[str]:
    output_dir = _render_lilypond(ly_source, output_stem, svg=True, output_dir=output_dir)
    pages = collect_svg_pages(output_dir, output_stem)
    if not pages:
        raise FileNotFoundError("LilyPond did not produce SVG output")
    return pages


def render_svg(ly_source: str, output_stem: str = "score", output_dir: str | Path | None = None) -> str:
    """Backward-compatible helper returning the first rendered SVG page."""
    return render_svgs(ly_source, output_stem=output_stem, output_dir=output_dir)[0]


def render_pdf(ly_source: str, output_stem: str = "score", output_dir: str | Path | None = None) -> str:
    output_dir = _render_lilypond(ly_source, output_stem, svg=False, output_dir=output_dir)
    pdf_path = output_dir / f"{output_stem}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError("LilyPond did not produce PDF output")
    return str(pdf_path)
