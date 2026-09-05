"""Generate improvised melodies over chord changes.

The generator favors melodic continuity: small intervals, scale-wise fragments,
nearby chord-tone targets, occasional complete triplet cells, optional tritone
substitutions, and (v13) a melodic-temperature control that rewards motivic
continuity and bebop enclosures.
"""

from __future__ import annotations

import random
from music.chord_parser import (
    parse_chord,
    chord_scale_notes,
    root_pc,
    tritone_sub_symbol,
)
from music.groove import normalize_style
from music.scale_syllabus import scale_focus_notes


def _fold_range(pitch: int, low=60, high=84) -> int:
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return max(low, min(high, pitch))


def _unique_sorted(notes):
    return sorted(set(_fold_range(int(n)) for n in notes))


def _melodic_temp(value) -> float:
    """Normalize UI melodic temperature to 0.0..1.0."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = 35.0
    if n <= 1.0:
        return max(0.0, min(1.0, n))
    return max(0.0, min(1.0, n / 100.0))


def _nearest_pitch(targets, prev, max_distance=None):
    if not targets:
        return prev
    choices = []
    for note in targets:
        for octave_shift in (-12, 0, 12):
            p = _fold_range(note + octave_shift)
            dist = abs(p - prev)
            if max_distance is None or dist <= max_distance:
                choices.append((dist, p))
    if not choices:
        choices = [(abs(_fold_range(n) - prev), _fold_range(n)) for n in targets]
    choices.sort(key=lambda x: x[0])
    return choices[0][1]


def _choose_melodic_pitch(rng, chord_tones, scale_notes, prev, strong_beat=False, prefer_down=False, scale_focus=False):
    """Pick a pitch with a bias toward continuity and functional landings."""
    scale_notes = _unique_sorted(scale_notes or chord_tones)
    chord_tones = _unique_sorted(chord_tones or scale_notes)
    if prev is None:
        return rng.choice(chord_tones or scale_notes)

    source = chord_tones if strong_beat and rng.random() < (0.58 if scale_focus else 0.72) else scale_notes
    if scale_focus and not strong_beat and rng.random() < 0.78:
        neighbors = [n for n in scale_notes if 1 <= abs(n - prev) <= 2]
        if neighbors:
            return rng.choice(neighbors)
    max_step = 7 if (strong_beat and scale_focus) else (5 if strong_beat else 3)
    close = [n for n in source if abs(n - prev) <= max_step]
    if prefer_down:
        downward = [n for n in close if n <= prev]
        if downward:
            downward.sort(key=lambda n: (abs((prev - n) - 1), abs(n - prev)))
            return downward[0]
    if close:
        return rng.choice(close)

    return _nearest_pitch(source, prev, max_distance=7)


def _maybe_tritone_sub(sym: str, next_sym: str | None, prev_pitch: int | None, rng: random.Random) -> tuple[str, bool]:
    sub = tritone_sub_symbol(sym, prefer_flats=True)
    if not sub:
        return sym, False

    probability = 0.18
    sub_pc = root_pc(sub)
    next_pc = root_pc(next_sym) if next_sym else None
    if sub_pc is not None and next_pc is not None and (sub_pc - next_pc) % 12 == 1:
        probability = 0.62

    if prev_pitch is not None:
        sub_scale = _unique_sorted(chord_scale_notes(sub, octave=5))
        if any(0 <= prev_pitch - n <= 2 for n in sub_scale):
            probability = max(probability, 0.70)

    use_sub = rng.random() < probability
    return (sub if use_sub else sym), use_sub


def _guide_tones(chord_tones):
    tones = _unique_sorted(chord_tones)
    if len(tones) >= 4:
        return [tones[1], tones[3]]  # practical 3rd/7th approximation from parser order
    if len(tones) >= 2:
        return [tones[1]]
    return tones


def _new_motive(rng):
    """Create a small interval/rhythm idea that can be sequenced over later chords."""
    intervals = rng.choice([
        [2, -1, 2],
        [-2, -1, -2],
        [1, 2, -1],
        [-1, -2, 1],
        [2, 2, -1, -2],
        [-2, 1, -2, -1],
    ])
    durations = rng.choice([
        [0.5, 0.5, 0.5, 0.5],
        [0.5, 0.5, 1.0],
        [1.0, 0.5, 0.5],
    ])
    return {"intervals": intervals, "durations": durations, "uses": 0, "id": f"mot_{rng.randrange(1_000_000)}"}


def _pitch_near_desired(desired, pool, prev):
    pool = _unique_sorted(pool)
    if not pool:
        return _fold_range(desired)
    choices = []
    for n in pool:
        for shift in (-12, 0, 12):
            p = _fold_range(n + shift)
            choices.append((abs(p - desired), abs(p - prev), p))
    choices.sort()
    return choices[0][2]


def _motive_cell(rng, motive, chord_tones, scale_notes, start, end, prev, temp, prefer_down=False, scale_focus=False):
    durations = motive["durations"]
    total = sum(durations)
    if start + total > end + 0.001:
        return None, prev, start
    events = []
    pitch = _choose_melodic_pitch(rng, chord_tones, scale_notes, prev, strong_beat=True, prefer_down=prefer_down, scale_focus=scale_focus)
    for i, dur in enumerate(durations):
        if i > 0:
            interval = motive["intervals"][(i - 1) % len(motive["intervals"])]
            desired = pitch + interval
            pool = scale_notes if rng.random() < 0.72 + 0.18 * temp else chord_tones
            pitch = _pitch_near_desired(desired, pool, pitch)
        events.append({
            "pitch": pitch,
            "start": start + sum(durations[:i]),
            "duration": max(0.25, dur * 0.88),
            "velocity": rng.randint(66, 94),
            "motive_id": motive["id"],
            "motive_use": motive["uses"],
        })
    motive["uses"] += 1
    return events, pitch, start + total


def _enclosure_cell(rng, chord_tones, scale_notes, start, end, prev, temp, prefer_down=False):
    """Three eighth-note bebop enclosure resolving to a guide/chord tone."""
    total = 1.5
    if start + total > end + 0.001:
        return None, prev, start
    targets = _guide_tones(chord_tones) or chord_tones
    if not targets:
        return None, prev, start
    target = _nearest_pitch(targets, prev if prev is not None else targets[0], max_distance=9)
    # Above/below/target is the classic visible behavior; sometimes invert it.
    if prefer_down or rng.random() < 0.60 + 0.25 * temp:
        notes = [_fold_range(target + rng.choice([1, 2])), _fold_range(target - 1), target]
    else:
        notes = [_fold_range(target - rng.choice([1, 2])), _fold_range(target + 1), target]
    events = []
    for i, pitch in enumerate(notes):
        events.append({
            "pitch": pitch,
            "start": start + i * 0.5,
            "duration": 0.44,
            "velocity": rng.randint(66, 94) + (6 if i == 2 else 0),
            "enclosure": True,
            "target_pitch": target,
        })
    return events, target, start + total


def generate_solo(
    chord_sequence: list[dict],
    style: str = "jazz",
    octave: int = 5,
    seed: int | None = None,
    scale_focus: bool = False,
    melodic_temperature: float | int = 35,
) -> list[dict]:
    style = normalize_style(style)
    rng = random.Random(seed)
    events: list[dict] = []
    cursor = 0.0
    prev_pitch = None
    temp = _melodic_temp(melodic_temperature)
    motive_context = {"motive": None, "phrase_index": 0}

    for i, chord in enumerate(chord_sequence):
        original_sym = chord["symbol"]
        # Cells carry their absolute grid position so empty measures become
        # rests instead of silently shifting later chords earlier in time.
        cursor = float(chord.get("start", cursor))
        nxt = chord_sequence[i + 1] if i + 1 < len(chord_sequence) else None
        next_sym = nxt["symbol"] if nxt else None
        sym, using_sub = _maybe_tritone_sub(original_sym, next_sym, prev_pitch, rng)
        dur = float(chord.get("duration", 4.0))
        if nxt is not None and "start" in nxt:
            gap_to_next = float(nxt["start"]) - cursor
            if 0 < gap_to_next < dur:
                dur = gap_to_next
        chord_tones = _unique_sorted(parse_chord(sym, octave=octave))
        scale = _unique_sorted(scale_focus_notes(sym, octave=octave, rng=rng) if scale_focus else chord_scale_notes(sym, octave=octave))
        if not chord_tones:
            cursor += dur
            continue
        if style in {"bossa", "samba"}:
            phrase, prev_pitch = _lyrical_phrase(rng, chord_tones, scale, cursor, dur, prev_pitch, samba=(style == "samba"), prefer_down=using_sub, scale_focus=scale_focus, melodic_temperature=temp)
        elif style == "pop":
            phrase, prev_pitch = _sparse_phrase(rng, chord_tones, scale, cursor, dur, prev_pitch, prefer_down=using_sub, scale_focus=scale_focus)
        else:
            phrase, prev_pitch = _bebop_phrase(rng, chord_tones, scale, cursor, dur, prev_pitch, prefer_down=using_sub, scale_focus=scale_focus, melodic_temperature=temp, motive_context=motive_context)
        events.extend(phrase)
        cursor += dur
    return events


def _triplet_group(rng, chord_tones, scale_notes, start, end, prev, prefer_down=False, scale_focus=False):
    """Emit one complete triplet cell, with rests allowed inside it."""
    unit = rng.choice([1.0 / 3.0, 2.0 / 3.0])
    total = unit * 3.0
    if start + total > end + 0.001:
        return None, prev, start

    group_id = f"tr_{start:.4f}_{rng.randrange(1_000_000)}"
    events = []
    sounding_slots = []
    for slot in range(3):
        if rng.random() > 0.28:
            sounding_slots.append(slot)
    if not sounding_slots:
        sounding_slots.append(rng.randrange(3))

    for slot in range(3):
        slot_start = start + slot * unit
        if slot not in sounding_slots:
            continue
        strong = slot == 0 and abs(slot_start - round(slot_start)) < 0.001
        pitch = _choose_melodic_pitch(rng, chord_tones, scale_notes, prev, strong_beat=strong, prefer_down=prefer_down, scale_focus=scale_focus)
        events.append({
            "pitch": pitch,
            "start": slot_start,
            "duration": unit * 0.90,
            "velocity": rng.randint(64, 92),
            "tuplet": "triplet",
            "tuplet_group": group_id,
            "tuplet_start": start,
            "tuplet_unit": unit,
            "tuplet_slot": slot,
        })
        prev = pitch
    return events, prev, start + total


def _bebop_phrase(rng, chord_tones, scale_notes, start, duration, prev, prefer_down=False, scale_focus=False, melodic_temperature=0.35, motive_context=None):
    events = []
    t = start
    end = start + duration
    prev = prev if prev is not None else rng.choice(chord_tones)
    eighth_run_remaining = 0
    temp = _melodic_temp(melodic_temperature)
    motive_context = motive_context if motive_context is not None else {"motive": None}

    if motive_context.get("motive") is None or rng.random() < 0.10 + 0.22 * temp:
        motive_context["motive"] = _new_motive(rng)

    if duration >= 1.0 and rng.random() < max(0.35, 0.74 - 0.18 * temp):
        t += 0.5

    while t < end - 0.01:
        on_beat = abs((t - round(t))) < 0.001
        room = end - t

        if room >= 1.5 and rng.random() < 0.05 + 0.20 * temp:
            enc, prev, new_t = _enclosure_cell(rng, chord_tones, scale_notes, t, end, prev, temp, prefer_down=prefer_down)
            if enc is not None:
                events.extend(enc)
                t = new_t
                continue

        if room >= 1.5 and rng.random() < 0.06 + 0.38 * temp:
            mot, prev, new_t = _motive_cell(rng, motive_context["motive"], chord_tones, scale_notes, t, end, prev, temp, prefer_down=prefer_down, scale_focus=scale_focus)
            if mot is not None:
                events.extend(mot)
                t = new_t
                continue

        if eighth_run_remaining <= 0 and room >= 1.0 and rng.random() < 0.125:
            trip, prev, new_t = _triplet_group(rng, chord_tones, scale_notes, t, end, prev, prefer_down=prefer_down, scale_focus=scale_focus)
            if trip is not None:
                events.extend(trip)
                t = new_t
                continue

        if eighth_run_remaining <= 0 and rng.random() < max(0.02, 0.10 - 0.05 * temp):
            t += 0.5
            continue

        if eighth_run_remaining <= 0 and room >= 1.5 and rng.random() < 0.30 + 0.28 * temp:
            eighth_run_remaining = rng.choice([3, 4, 5, 6, 7, 8] if temp > 0.55 else [3, 4, 5, 6])

        if eighth_run_remaining > 0:
            dur = 0.5
            eighth_run_remaining -= 1
        else:
            dur = rng.choices([0.5, 0.75, 1.0], weights=[10 + int(8 * temp), 1, 2], k=1)[0]

        if t + dur > end:
            dur = end - t
        pitch = _choose_melodic_pitch(rng, chord_tones, scale_notes, prev, strong_beat=on_beat, prefer_down=prefer_down, scale_focus=scale_focus)
        events.append({"pitch": pitch, "start": t, "duration": max(0.25, dur * 0.88), "velocity": rng.randint(65, 94)})
        prev = pitch
        t += dur
    return events, prev


def _lyrical_phrase(rng, chord_tones, scale_notes, start, duration, prev, samba=False, prefer_down=False, scale_focus=False, melodic_temperature=0.35):
    events = []
    prev = prev if prev is not None else rng.choice(chord_tones)
    t = start
    end = start + duration
    temp = _melodic_temp(melodic_temperature)
    rhythm_pool = [0.5, 1.0, 1.5] if not samba else [0.5, 0.5, 1.0, 1.0]
    rest_chance = max(0.12, (0.28 if not samba else 0.16) - 0.07 * temp)
    while t < end - 0.01:
        if end - t >= 1.0 and rng.random() < 0.18:
            trip, prev, new_t = _triplet_group(rng, chord_tones, scale_notes, t, end, prev, prefer_down=prefer_down, scale_focus=scale_focus)
            if trip is not None:
                events.extend(trip)
                t = new_t
                continue
        dur = rng.choice(rhythm_pool)
        if t + dur > end:
            dur = end - t
        if rng.random() < rest_chance:
            t += dur
            continue
        strong = abs((t - round(t))) < 0.001
        pitch = _choose_melodic_pitch(rng, chord_tones, scale_notes, prev, strong_beat=strong, prefer_down=prefer_down, scale_focus=scale_focus)
        events.append({"pitch": pitch, "start": t, "duration": max(0.25, dur * 0.85), "velocity": rng.randint(55, 84 if samba else 78)})
        prev = pitch
        t += dur
    return events, prev


def _sparse_phrase(rng, chord_tones, scale_notes, start, duration, prev, prefer_down=False, scale_focus=False):
    events = []
    prev = prev if prev is not None else rng.choice(chord_tones)
    beats = int(round(duration))
    for beat in range(beats):
        if rng.random() < 0.45:
            continue
        t = start + beat
        pitch = _choose_melodic_pitch(rng, chord_tones, scale_notes, prev, strong_beat=True, prefer_down=prefer_down, scale_focus=scale_focus)
        events.append({"pitch": pitch, "start": t, "duration": 0.75, "velocity": rng.randint(58, 80)})
        prev = pitch
    return events, prev
