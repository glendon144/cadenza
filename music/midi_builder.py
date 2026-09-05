"""Assemble MIDI from chord grid plus generated bass and solo parts."""

from __future__ import annotations

from pathlib import Path
from midiutil import MIDIFile
from music.voicing import voice_chord
from music.bassline import generate_bassline
from music.improv import generate_solo
from music.groove import LATIN_STYLES, clave_offsets_for_measure, normalize_groove, normalize_style
from music.drums import generate_drum_track
from music.rms_phrasing import warp_solo_events

CHANNEL_CHORD = 0
CHANNEL_BASS = 1
CHANNEL_SOLO = 2
CHANNEL_DRUMS = 9
PROGRAM_PIANO = 0
PROGRAM_ACOUSTIC_BASS = 32
PROGRAM_TRUMPET = 56

# Mixer strips, in MIDI track order.
MIXER_TRACKS = ("rhythm", "bass", "solo", "drums")
_MIXER_CHANNELS = (CHANNEL_CHORD, CHANNEL_BASS, CHANNEL_SOLO, CHANNEL_DRUMS)
MIXER_DEFAULT_VOLUME = 80


def _clamp_mixer_volume(value, default: int = MIXER_DEFAULT_VOLUME) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(100, n))


def normalize_mixer(mixer: dict | None) -> dict:
    """Return complete, clamped mixer strips for every track.

    Unknown tracks and keys are dropped, missing ones get console defaults,
    and volumes are clamped to 0-100. Safe to persist as-is.
    """
    strips = {}
    for name in MIXER_TRACKS:
        raw = (mixer or {}).get(name) or {}
        if not isinstance(raw, dict):
            raw = {}
        strips[name] = {
            "active": bool(raw.get("active", True)),
            "mute": bool(raw.get("mute", False)),
            "solo": bool(raw.get("solo", False)),
            "volume": _clamp_mixer_volume(raw.get("volume", MIXER_DEFAULT_VOLUME)),
        }
    return strips


def mixer_levels(mixer: dict | None) -> dict:
    """Resolve mixer strips to per-track include flags and CC7 volume levels.

    Semantics follow a physical console: an inactive channel is pulled from
    the session entirely (its notes are dropped from the MIDI); mute keeps
    the notes but silences the channel; any active solo silences every
    non-soloed channel; volume maps 0-100 onto MIDI channel volume 0-127.
    """
    strips = normalize_mixer(mixer)
    any_solo = any(s["solo"] and s["active"] for s in strips.values())
    levels = {}
    for name, s in strips.items():
        audible = s["active"] and not s["mute"] and (not any_solo or s["solo"])
        levels[name] = {
            "include": s["active"],
            "cc7": round(s["volume"] * 127 / 100) if audible else 0,
        }
    return levels


def stem_mixer(part: str) -> dict:
    """Mixer that isolates one part at full volume, for rendering stems.

    A stem carries the part at CC7 127 so the browser can apply the console
    level itself; every other part is inactive and dropped from the file.
    """
    if part not in MIXER_TRACKS:
        raise ValueError(f"Unknown mixer part: {part!r}")
    return {
        name: {"active": name == part, "mute": False, "solo": False, "volume": 100}
        for name in MIXER_TRACKS
    }


def _note_event(pitch: int, start: float, duration: float, velocity: int, hand: str | None = None) -> dict:
    evt = {"pitch": int(pitch), "start": float(start), "duration": float(duration), "velocity": int(velocity)}
    if hand:
        evt["hand"] = hand
    return evt


def _latin_comp_events(cell: dict, voiced: dict, style: str, groove: str, beats_per_measure: int) -> list[dict]:
    """Clave-aware piano/guitar-style stabs for bossa and samba."""
    events: list[dict] = []
    measure = int(cell["measure"])
    cell_start = measure * beats_per_measure + int(cell.get("beat", 0))
    cell_end = cell_start + float(cell.get("duration", beats_per_measure))
    offsets = clave_offsets_for_measure(measure, groove, style)
    right = list(voiced.get("right", []))
    left = [p for p in voiced.get("left", []) if p >= 45]  # keep comping left hand out of the bass player's way
    chord = sorted(set(left + right)) or right
    if not chord:
        return events

    base_velocity = 74 if style == "bossa" else 84
    dur = 0.55 if style == "bossa" else 0.38
    for n, offset in enumerate(offsets):
        start = measure * beats_per_measure + offset
        if start < cell_start - 0.001 or start >= cell_end - 0.001:
            continue
        vel = base_velocity + (6 if n == 0 else 0)
        for pitch in chord:
            if 0 <= pitch <= 127:
                events.append(_note_event(pitch, start, min(dur, cell_end - start), vel, "right" if pitch >= 60 else "left"))
    return events


def _sustained_chord_events(cell: dict, voiced: dict, beats_per_measure: int) -> list[dict]:
    events: list[dict] = []
    start = int(cell["measure"]) * beats_per_measure + int(cell.get("beat", 0))
    dur = float(cell.get("duration", beats_per_measure))
    for pitch in voiced["right"]:
        if 0 <= pitch <= 127:
            events.append(_note_event(pitch, start, dur * 0.95, 70, "right"))
    for pitch in voiced["left"]:
        if 0 <= pitch <= 127:
            events.append(_note_event(pitch, start, dur * 0.95, 65, "left"))
    return events



def _phrase_metadata(solo_events: list[dict]) -> dict:
    motives = sorted({e.get("motive_id") for e in solo_events if e.get("motive_id")})
    return {
        "motive_count": len(motives),
        "motive_event_count": sum(1 for e in solo_events if e.get("motive_id")),
        "enclosure_count": sum(1 for e in solo_events if e.get("enclosure")),
    }


def build_arrangement(
    chord_grid: list[dict],
    style: str = "jazz",
    groove: str = "auto",
    time_sig: tuple[int, int] = (4, 4),
    seed: int | None = None,
    scale_focus: bool = False,
    choruses: int = 1,
    melodic_temperature: float | int = 35,
    rms_phrasing: bool = False,
    measures: int | None = None,
) -> dict:
    style = normalize_style(style)
    groove = normalize_groove(groove, style)
    beats_per_measure = int(time_sig[0])
    choruses = max(1, min(20, int(choruses or 1)))
    sequence = sorted(chord_grid, key=lambda c: (int(c["measure"]), int(c.get("beat", 0))))
    base_measures = max((int(c["measure"]) for c in sequence), default=3) + 1
    if measures:
        # The song's declared bar count wins when it is longer, so trailing
        # rest measures stay in the form instead of the next chorus starting early.
        base_measures = max(base_measures, int(measures))
    chorus_beats = base_measures * beats_per_measure

    expanded_sequence: list[dict] = []
    for chorus in range(choruses):
        offset_beats = chorus * chorus_beats
        offset_measures = chorus * base_measures
        for c in sequence:
            clone = dict(c)
            clone["measure"] = int(c["measure"]) + offset_measures
            expanded_sequence.append(clone)

    chord_seq = [
        {
            "symbol": c["symbol"],
            "start": int(c["measure"]) * beats_per_measure + int(c.get("beat", 0)),
            "duration": float(c.get("duration", beats_per_measure)),
        }
        for c in expanded_sequence
    ]

    chord_events: list[dict] = []
    for cell in expanded_sequence:
        sym = cell["symbol"]
        voiced = voice_chord(sym, style=style)
        if style in LATIN_STYLES:
            chord_events.extend(_latin_comp_events(cell, voiced, style, groove, beats_per_measure))
        else:
            chord_events.extend(_sustained_chord_events(cell, voiced, beats_per_measure))

    bassline = [e for e in generate_bassline(chord_seq, style=style, beats_per_measure=beats_per_measure, seed=seed, scale_focus=scale_focus) if 0 <= e["pitch"] <= 127]

    solo: list[dict] = []
    prev_chorus_solo_end = 0.0
    for chorus in range(choruses):
        chorus_cells = [
            {
                "symbol": c["symbol"],
                "start": int(c["measure"]) * beats_per_measure + int(c.get("beat", 0)),
                "duration": float(c.get("duration", beats_per_measure)),
            }
            for c in sequence
        ]
        chorus_seed = (seed or 0) + 1 + chorus * 7919
        chorus_solo = generate_solo(chorus_cells, style=style, octave=5, seed=chorus_seed, scale_focus=scale_focus, melodic_temperature=melodic_temperature)
        for e in chorus_solo:
            clone = dict(e)
            clone["start"] = float(e["start"]) + chorus * chorus_beats
            if "tuplet_start" in clone:
                clone["tuplet_start"] = float(clone["tuplet_start"]) + chorus * chorus_beats
            if "tuplet_group" in clone:
                clone["tuplet_group"] = f"ch{chorus}_" + str(clone["tuplet_group"])
            if 0 <= clone["pitch"] <= 127:
                solo.append(clone)
        prev_chorus_solo_end = (chorus + 1) * chorus_beats

    total_measures = base_measures * choruses
    drum_events = generate_drum_track(total_measures, style=style, groove=groove, beats_per_measure=beats_per_measure, seed=seed)
    return {
        "chord_events": chord_events,
        "bass_events": bassline,
        "solo_events": solo,
        "drum_events": drum_events,
        "chord_cells": expanded_sequence,
        "total_beats": total_measures * beats_per_measure,
        "base_measures": base_measures,
        "choruses": choruses,
        "beats_per_measure": beats_per_measure,
        "style": style,
        "groove": groove,
        "scale_focus": bool(scale_focus),
        "melodic_temperature": melodic_temperature,
        "rms_phrasing": bool(rms_phrasing),
        "phrase_metadata": _phrase_metadata(solo),
    }


def build_midi(
    chord_grid: list[dict],
    tempo: int = 120,
    style: str = "jazz",
    groove: str = "auto",
    time_sig: tuple[int, int] = (4, 4),
    seed: int | None = None,
    scale_focus: bool = False,
    choruses: int = 1,
    melodic_temperature: float | int = 35,
    rms_phrasing: bool = False,
    measures: int | None = None,
    output_path: str | Path | None = None,
) -> str:
    arrangement = build_arrangement(chord_grid, style=style, groove=groove, time_sig=time_sig, seed=seed, scale_focus=scale_focus, choruses=choruses, melodic_temperature=melodic_temperature, rms_phrasing=rms_phrasing, measures=measures)
    return write_midi(arrangement, tempo=tempo, output_path=output_path)



def _swing_amount_for_tempo(tempo: int) -> float:
    """Tempo-sensitive bebop swing offset in quarter-note beat units.

    Slow tempos can lean toward a 12/8 grid, but faster bebop tempos should
    approach nearly straight eighths.  This avoids the square/ragtime effect
    of using one fixed triplet delay at every tempo.
    """
    tempo = max(40, min(320, int(tempo or 120)))
    points = [
        (80, 0.155),   # close to 12/8 long-short feel
        (120, 0.115),
        (160, 0.075),
        (210, 0.040),
        (280, 0.018),  # fast lines become almost even eighths
    ]
    if tempo <= points[0][0]:
        return points[0][1]
    for (t0, s0), (t1, s1) in zip(points, points[1:]):
        if tempo <= t1:
            frac = (tempo - t0) / (t1 - t0)
            return s0 + (s1 - s0) * frac
    return points[-1][1]


def _jazz_playback_event(start: float, duration: float, velocity: int, tempo: int) -> tuple[float, float, int]:
    """Apply subtle playback-only swing, articulation, and upbeat accenting.

    The notation remains clean eighth notes. Playback gets the Parker-era idea:
    the faster the tempo, the straighter the eighths, with more of the swing
    carried by articulation and accent rather than an obvious triplet lilt.
    """
    frac = start - int(start)
    vel = int(velocity)
    dur = float(duration)
    if abs(frac - 0.5) < 0.03:
        swing = _swing_amount_for_tempo(tempo)
        start = start + swing
        dur = max(0.16, dur - swing * 0.25)
        vel = min(127, vel + 7)
    elif abs(frac) < 0.03:
        vel = max(1, vel - 2)
        dur = dur * 0.96
    else:
        # Triplets and sixteenths should not get a mechanical eighth-note shove,
        # but a little separation keeps the trumpet line from sounding organ-like.
        dur = dur * 0.94
    return start, dur, vel

def write_midi(arrangement: dict, tempo: int = 120, output_path: str | Path | None = None, mixer: dict | None = None) -> str:
    if output_path is None:
        raise ValueError("write_midi now requires output_path so renders do not overwrite each other.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    levels = mixer_levels(mixer) if mixer is not None else None

    def _include(name: str) -> bool:
        return levels is None or levels[name]["include"]

    midi = MIDIFile(4, deinterleave=False)
    beats_per_measure = int(arrangement.get("beats_per_measure", 4))
    programs = [PROGRAM_PIANO, PROGRAM_ACOUSTIC_BASS, PROGRAM_TRUMPET]
    for track in range(4):
        midi.addTempo(track, 0, int(tempo))
        midi.addTimeSignature(track, 0, beats_per_measure, 2, 24)
        if track < 3:
            midi.addProgramChange(track, track, 0, programs[track])
        if levels is not None:
            # Mixer volumes ride on MIDI channel volume so muted/soloed-away
            # parts stay in the file but render silent, keeping full length.
            midi.addControllerEvent(track, _MIXER_CHANNELS[track], 0, 7, levels[MIXER_TRACKS[track]]["cc7"])

    if _include("rhythm"):
        for evt in arrangement["chord_events"]:
            midi.addNote(0, CHANNEL_CHORD, int(evt["pitch"]), float(evt["start"]), float(evt["duration"]), int(evt["velocity"]))
    if _include("bass"):
        for evt in arrangement["bass_events"]:
            midi.addNote(1, CHANNEL_BASS, int(evt["pitch"]), float(evt["start"]), float(evt["duration"]), int(evt["velocity"]))
    if _include("solo"):
        solo_events_for_playback = arrangement["solo_events"]
        if arrangement.get("rms_phrasing"):
            solo_events_for_playback = warp_solo_events(solo_events_for_playback, tempo=tempo, intensity=1.0)
        for evt in solo_events_for_playback:
            start = float(evt["start"])
            duration = float(evt["duration"])
            velocity = int(evt["velocity"])
            if arrangement.get("style") == "jazz":
                start, duration, velocity = _jazz_playback_event(start, duration, velocity, tempo)
            midi.addNote(2, CHANNEL_SOLO, int(evt["pitch"]), start, duration, velocity)
    if _include("drums"):
        for evt in arrangement.get("drum_events", []):
            start = float(evt["start"])
            duration = float(evt["duration"])
            velocity = int(evt["velocity"])
            if arrangement.get("style") == "jazz" and int(evt.get("pitch", 0)) in {51, 42}:
                start, duration, velocity = _jazz_playback_event(start, duration, velocity, tempo)
            midi.addNote(3, CHANNEL_DRUMS, int(evt["pitch"]), start, duration, velocity)

    with output_path.open("wb") as f:
        midi.writeFile(f)
    return str(output_path)
