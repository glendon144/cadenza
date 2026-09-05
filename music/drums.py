"""Style-aware drum-set generation for ChordCraft."""

from __future__ import annotations

import random
from music.groove import LATIN_STYLES, clave_offsets_for_measure, normalize_groove, normalize_style

# General MIDI percussion note numbers (channel 10 / zero-based channel 9).
KICK = 36
SNARE = 38
CROSS_STICK = 37
CLOSED_HAT = 42
OPEN_HAT = 46
RIDE = 51
CRASH = 49
LOW_TOM = 45
MID_TOM = 47
HIGH_TOM = 50
PEDAL_HAT = 44

DRUM_NAMES = {
    KICK: "kick",
    SNARE: "snare",
    CROSS_STICK: "cross_stick",
    CLOSED_HAT: "closed_hat",
    OPEN_HAT: "open_hat",
    RIDE: "ride",
    CRASH: "crash",
    LOW_TOM: "low_tom",
    MID_TOM: "mid_tom",
    HIGH_TOM: "high_tom",
    PEDAL_HAT: "pedal_hat",
}


def _event(pitch: int, start: float, duration: float = 0.18, velocity: int = 76) -> dict:
    return {
        "pitch": int(pitch),
        "start": round(float(start), 4),
        "duration": round(float(duration), 4),
        "velocity": max(1, min(127, int(velocity))),
        "drum": DRUM_NAMES.get(int(pitch), "drum"),
    }


def _add(events: list[dict], pitch: int, start: float, duration: float = 0.18, velocity: int = 76) -> None:
    if start >= -0.001:
        events.append(_event(pitch, start, duration, velocity))


def _add_crash_on_first(events: list[dict], measure_start: float, measure: int) -> None:
    if measure == 0:
        _add(events, CRASH, measure_start, 0.45, 82)


def _jazz_measure(measure: int, measure_start: float, rng: random.Random) -> list[dict]:
    """Bebop-ish ride pattern with feathered bass drum and sparse comping."""
    events: list[dict] = []
    _add_crash_on_first(events, measure_start, measure)
    # Notated mostly as eighths; playback swing is applied in midi_builder.
    ride_pattern = [0.0, 1.0, 1.5, 2.0, 3.0, 3.5]
    for i, off in enumerate(ride_pattern):
        _add(events, RIDE, measure_start + off, 0.28, 78 if i in (0, 3) else 68)
    for off in (1.0, 3.0):
        _add(events, PEDAL_HAT, measure_start + off, 0.12, 58)
    # Feather the four: felt more than heard.
    for off in (0.0, 1.0, 2.0, 3.0):
        _add(events, KICK, measure_start + off, 0.12, 34)
    # Occasional snare comping, enough to feel alive without cluttering the line.
    comp_pool = [0.5, 1.75, 2.5, 3.25]
    for off in comp_pool:
        if rng.random() < 0.22:
            _add(events, SNARE, measure_start + off, 0.12, 52)
    return events


def _pop_measure(measure: int, measure_start: float, rng: random.Random) -> list[dict]:
    events: list[dict] = []
    _add_crash_on_first(events, measure_start, measure)
    for off in [i * 0.5 for i in range(8)]:
        _add(events, CLOSED_HAT, measure_start + off, 0.16, 54 if off % 1 else 62)
    for off in (0.0, 2.0):
        _add(events, KICK, measure_start + off, 0.16, 78)
    if rng.random() < 0.45:
        _add(events, KICK, measure_start + 2.5, 0.14, 60)
    for off in (1.0, 3.0):
        _add(events, SNARE, measure_start + off, 0.18, 82)
    return events


def _bossa_measure(measure: int, measure_start: float, groove: str) -> list[dict]:
    events: list[dict] = []
    _add_crash_on_first(events, measure_start, measure)
    # Light eighth-note hat/brush feel.
    for off in [i * 0.5 for i in range(8)]:
        _add(events, CLOSED_HAT, measure_start + off, 0.12, 42 if off % 1 else 50)
    # Bossa bass drum: root-root, fifth-fifth echo of the bassline concept.
    for off, vel in ((0.0, 64), (1.5, 48), (2.0, 62), (3.5, 48)):
        _add(events, KICK, measure_start + off, 0.15, vel)
    for off in clave_offsets_for_measure(measure, groove, "bossa"):
        _add(events, CROSS_STICK, measure_start + off, 0.12, 66)
    return events


def _samba_measure(measure: int, measure_start: float, groove: str) -> list[dict]:
    events: list[dict] = []
    _add_crash_on_first(events, measure_start, measure)
    # Busy sixteenth-like hat simplified to off/on eighth texture for readability.
    for off in [i * 0.5 for i in range(8)]:
        _add(events, CLOSED_HAT, measure_start + off, 0.10, 58 if off % 1 else 66)
    # Surdo-like bass drum pulse.
    for off, vel in ((0.0, 78), (1.5, 58), (2.0, 82), (3.5, 58)):
        _add(events, KICK, measure_start + off, 0.16, vel)
    # Snare/cross-stick clave layer.
    for off in clave_offsets_for_measure(measure, groove, "samba"):
        _add(events, CROSS_STICK, measure_start + off, 0.11, 74)
    # Light backbeat lift on 2 and 4.
    for off in (1.0, 3.0):
        _add(events, SNARE, measure_start + off, 0.12, 48)
    return events


def generate_drum_track(
    total_measures: int,
    style: str = "jazz",
    groove: str = "auto",
    beats_per_measure: int = 4,
    seed: int | None = None,
) -> list[dict]:
    """Generate a full drum-set part matching the current ChordCraft style."""
    style = normalize_style(style)
    groove = normalize_groove(groove, style)
    rng = random.Random((seed or 0) + 424242)
    events: list[dict] = []
    for measure in range(max(1, int(total_measures))):
        measure_start = measure * beats_per_measure
        if style == "jazz":
            events.extend(_jazz_measure(measure, measure_start, rng))
        elif style == "bossa":
            events.extend(_bossa_measure(measure, measure_start, groove))
        elif style == "samba":
            events.extend(_samba_measure(measure, measure_start, groove))
        else:
            events.extend(_pop_measure(measure, measure_start, rng))
    return sorted(events, key=lambda e: (float(e["start"]), int(e["pitch"])))
