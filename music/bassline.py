"""Generate bass lines over a chord progression."""

from __future__ import annotations

import random
from music.chord_parser import parse_chord, root_midi, root_pc, tritone_sub_symbol
from music.scale_syllabus import scale_focus_notes
from music.groove import normalize_style


def _fit(pitch: int, low=28, high=55) -> int:
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return max(low, min(high, pitch))



def _maybe_tritone_sub(sym: str, next_sym: str | None, rng: random.Random) -> str:
    sub = tritone_sub_symbol(sym, prefer_flats=True)
    if not sub:
        return sym
    probability = 0.22
    if next_sym:
        sub_pc = root_pc(sub)
        next_pc = root_pc(next_sym)
        # Strongly favor the classic downward half-step resolution, e.g.
        # Dm7 G7 Cmaj7 can become Dm7 Db7 Cmaj7 in the bass.
        if sub_pc is not None and next_pc is not None and (sub_pc - next_pc) % 12 == 1:
            probability = 0.78
    return sub if rng.random() < probability else sym

def generate_bassline(chord_sequence: list[dict], style: str = "jazz", beats_per_measure: int = 4, seed: int | None = None, scale_focus: bool = False) -> list[dict]:
    style = normalize_style(style)
    rng = random.Random(seed)
    events: list[dict] = []
    cursor = 0.0

    for i, chord in enumerate(chord_sequence):
        sym = chord["symbol"]
        # Cells carry their absolute grid position so empty measures become
        # rests instead of silently shifting later chords earlier in time.
        cursor = float(chord.get("start", cursor))
        dur = float(chord.get("duration", beats_per_measure))
        nxt = chord_sequence[i + 1] if i + 1 < len(chord_sequence) else None
        next_sym = nxt["symbol"] if nxt else sym
        if nxt is not None and "start" in nxt:
            gap_to_next = float(nxt["start"]) - cursor
            if 0 < gap_to_next < dur:
                dur = gap_to_next
        effective_sym = _maybe_tritone_sub(sym, next_sym, rng)
        root = _fit(root_midi(effective_sym, octave=2, prefer_slash_bass=True))
        tones = [_fit(n) for n in parse_chord(effective_sym, octave=2)]
        scale_tones = [_fit(n) for n in scale_focus_notes(effective_sym, octave=2, rng=rng)] if scale_focus else tones
        next_root = _fit(root_midi(next_sym, octave=2, prefer_slash_bass=True))

        if style in {"bossa", "samba"}:
            events.extend(_bossa_bass(root, cursor, dur, samba=(style == "samba")))
        elif style == "pop":
            events.extend(_pop_bass(root, cursor, dur))
        else:
            events.extend(_walking_bass(rng, root, tones, next_root, cursor, dur, scale_tones=scale_tones, scale_focus=scale_focus))
        cursor += dur
    return events


def _walking_bass(rng, root, tones, next_root, start, duration, scale_tones=None, scale_focus=False):
    events = []
    beats = max(1, int(round(duration)))
    for b in range(beats):
        if b == 0:
            pitch = root
        elif b == beats - 1 and beats > 1:
            direction = 1 if next_root >= root else -1
            pitch = next_root - direction
        elif scale_focus and scale_tones and b % 2 == 1:
            # Use chord-scale tones for horizontal continuity between roots.
            target = next_root if b >= beats - 2 else root
            candidates = sorted(scale_tones, key=lambda n: abs(n - target))[:5]
            pitch = rng.choice(candidates)
        elif tones and b % 2 == 1:
            pitch = rng.choice(tones)
        else:
            if scale_focus and scale_tones:
                pitch = rng.choice(scale_tones)
            else:
                pitch = root + rng.choice([0, 5, 7, 10, 12, -2])
        events.append({"pitch": _fit(pitch), "start": start + b, "duration": 0.88, "velocity": rng.randint(70, 90)})
    return events


def _bossa_bass(root, start, duration, samba=False):
    """Root-root, fifth-fifth bass with dotted-quarter/eighth motion.

    In each 4/4 measure the shape is:
      1 for dotted quarter, 1 for eighth, 5 for dotted quarter, 5 for eighth.
    This makes the style dropdown audibly different from straight walking bass.
    """
    events = []
    fifth = _fit(root + 7)
    remaining = float(duration)
    measure_start = float(start)
    vel_root = 92 if samba else 84
    vel_ghost = 76 if samba else 68
    vel_fifth = 88 if samba else 78
    while remaining > 0.01:
        span = min(4.0, remaining)
        pattern = [
            (0.0, root, 1.45, vel_root),
            (1.5, root, 0.42, vel_ghost),
            (2.0, fifth, 1.45, vel_fifth),
            (3.5, fifth, 0.42, vel_ghost),
        ]
        for offset, pitch, dur, vel in pattern:
            if offset < span - 0.01:
                events.append({"pitch": pitch, "start": measure_start + offset, "duration": min(dur, span - offset), "velocity": vel})
        measure_start += 4.0
        remaining -= 4.0
    return events


def _pop_bass(root, start, duration):
    events = []
    beats = max(1, int(round(duration)))
    for b in range(beats):
        if b % 4 == 0:
            pitch, vel = root, 92
        elif b % 4 == 2:
            pitch, vel = root + 12, 82
        else:
            continue
        events.append({"pitch": _fit(pitch, 28, 60), "start": start + b, "duration": 0.85, "velocity": vel})
    return events
