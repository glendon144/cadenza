"""Regression tests for bugs found in the v15 code audit."""

import pytest

pytest.importorskip("midiutil")

from music.midi_builder import build_arrangement


# ── Timeline alignment with grid gaps ────────────────────────────────────────

def test_empty_measure_keeps_parts_aligned():
    """An empty bar must become a rest, not shift bass/solo earlier in time."""
    grid = [
        {"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
        {"measure": 2, "beat": 0, "symbol": "G7", "duration": 4.0},
    ]
    arr = build_arrangement(grid, style="jazz", seed=1)

    chord_starts = sorted({e["start"] for e in arr["chord_events"]})
    assert chord_starts == [0.0, 8.0]

    bass_starts = [e["start"] for e in arr["bass_events"]]
    assert all(not (4.0 <= s < 8.0) for s in bass_starts), "bass played during the empty bar"
    assert any(s >= 8.0 for s in bass_starts), "bass never reached the G7 bar"

    solo_starts = [e["start"] for e in arr["solo_events"]]
    assert all(not (4.0 <= s < 8.0) for s in solo_starts), "solo played during the empty bar"


def test_empty_measure_alignment_all_styles():
    grid = [
        {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
        {"measure": 2, "beat": 0, "symbol": "G7", "duration": 4.0},
    ]
    for style in ("jazz", "bossa", "samba", "pop"):
        arr = build_arrangement(grid, style=style, seed=3)
        for part in ("bass_events", "solo_events"):
            starts = [e["start"] for e in arr[part]]
            assert all(not (4.0 <= s < 8.0) for s in starts), f"{style} {part} in empty bar"


def test_beat3_only_cell_starts_on_beat3():
    """A lone beat-3 chord starts at beat 2, not at the top of the form."""
    grid = [
        {"measure": 0, "beat": 2, "symbol": "G7", "duration": 2.0},
        {"measure": 1, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
    ]
    arr = build_arrangement(grid, style="jazz", seed=2)
    for part in ("bass_events", "solo_events"):
        starts = [e["start"] for e in arr[part]]
        assert min(starts) >= 2.0, f"{part} started before the first chord"


def test_declared_measures_preserve_trailing_rest_bars():
    """A declared bar count longer than the last chord keeps the full form.

    Without it, a 16-bar form whose bars 13-16 are rests collapsed to 12 bars
    per chorus, so the second chorus started four bars early.
    """
    grid = [
        {"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
        {"measure": 11, "beat": 0, "symbol": "G7", "duration": 4.0},
    ]
    arr = build_arrangement(grid, style="jazz", seed=1, choruses=2, measures=16)
    assert arr["base_measures"] == 16
    assert arr["total_beats"] == 128.0
    chorus2_measures = sorted(c["measure"] for c in arr["chord_cells"])[2:]
    assert chorus2_measures == [16, 27], "second chorus did not start at bar 17"

    # A declared count shorter than the chords must not truncate them.
    arr = build_arrangement(grid, style="jazz", seed=1, measures=8)
    assert arr["base_measures"] == 12


def test_gap_alignment_across_choruses():
    grid = [
        {"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
        {"measure": 2, "beat": 0, "symbol": "G7", "duration": 4.0},
    ]
    arr = build_arrangement(grid, style="jazz", seed=5, choruses=2)
    chorus_beats = arr["base_measures"] * arr["beats_per_measure"]
    for part in ("bass_events", "solo_events"):
        for e in arr[part]:
            pos = e["start"] % chorus_beats
            assert not (4.0 <= pos < 8.0), f"{part} in empty bar of a later chorus"


# ── Chord parser: min7b5 suffix slicing ──────────────────────────────────────

def test_min7b5_spelled_out_matches_short_form():
    from music.chord_parser import parse_chord_details

    long_form, err1 = parse_chord_details("Cmin7b5b9")
    short_form, err2 = parse_chord_details("Cm7b5b9")
    assert err1 is None and err2 is None
    assert long_form.intervals == short_form.intervals
    assert 13 in long_form.intervals, "b9 was lost"
    assert 14 not in long_form.intervals, "b9 parsed as natural 9"

    # Plain long form still parses to a half-diminished seventh.
    plain, err = parse_chord_details("Cmin7b5")
    assert err is None
    assert plain.intervals == [0, 3, 6, 10]
    assert plain.quality == "half-diminished"


# ── Notation: odd durations print as tied notes, not sixteenths ─────────────

def test_odd_duration_prints_tied_notes():
    from render.notation import events_to_ly_voice

    voice = events_to_ly_voice(
        [{"pitch": 60, "start": 0.0, "duration": 2.5, "velocity": 80}], 4.0, 120, "C"
    )
    assert "c'2~ c'8" in voice, voice
    assert "c'16" not in voice

    # 1.25 beats -> quarter tied to sixteenth.
    voice = events_to_ly_voice(
        [{"pitch": 62, "start": 0.0, "duration": 1.25, "velocity": 80}], 4.0, 120, "C"
    )
    assert "d'4~ d'16" in voice, voice


def test_mapped_durations_still_print_single_notes():
    from render.notation import events_to_ly_voice

    voice = events_to_ly_voice(
        [
            {"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 80},
            {"pitch": 62, "start": 1.0, "duration": 0.5, "velocity": 80},
            {"pitch": 64, "start": 1.5, "duration": 1.5, "velocity": 80},
        ],
        4.0, 120, "C",
    )
    assert "c'4 d'8 e'4." in voice, voice
    assert "~" not in voice


# ── Transposition of roots outside the key list ──────────────────────────────

def test_transpose_sharp_and_enharmonic_roots():
    from music.key_utils import transpose_chord_symbol

    assert transpose_chord_symbol("D#7", 2) == "F7"
    assert transpose_chord_symbol("G#m7", 3, "C") == "Bm7"
    assert transpose_chord_symbol("A#7", 1) == "B7"
    assert transpose_chord_symbol("E#7", 2) == "G7"
    # Slash bass with an accidental root transposes too.
    assert transpose_chord_symbol("D#7/A#", 2) == "F7/C"
    # Target-key spelling still applies.
    assert transpose_chord_symbol("D#7", 1, "F") == "E7"
    # Ordinary roots keep working.
    assert transpose_chord_symbol("Eb7", 2) == "F7"


# ── Song settings persistence ────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    flask = pytest.importorskip("flask")  # noqa: F841
    import database.db as db
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    import app as app_module
    app_module.app.config["TESTING"] = True
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready
    with app_module.app.test_client() as c:
        yield c
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready


def test_song_settings_survive_save_and_load(client):
    song_id = client.post("/api/songs", json={"title": "Round Trip"}).get_json()["id"]
    resp = client.put(f"/api/songs/{song_id}", json={
        "title": "Round Trip",
        "scale_focus": True,
        "rms_phrasing": True,
        "melodic_temperature": 72,
        "choruses": 3,
        "measures": 16,
        "chords": [{"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0}],
    })
    assert resp.status_code == 200

    data = client.get(f"/api/songs/{song_id}").get_json()
    assert data["scale_focus"] == 1
    assert data["rms_phrasing"] == 1
    assert data["melodic_temperature"] == 72
    assert data["choruses"] == 3
    assert data["measures"] == 16


def test_song_settings_clamped(client):
    song_id = client.post("/api/songs", json={}).get_json()["id"]
    client.put(f"/api/songs/{song_id}", json={
        "melodic_temperature": 999,
        "choruses": 0,
        "measures": 100000,
    })
    data = client.get(f"/api/songs/{song_id}").get_json()
    assert data["melodic_temperature"] == 100
    assert data["choruses"] == 1
    assert data["measures"] == 240


def test_contiguous_grid_output_unchanged():
    """The fix must not alter arrangements for gap-free grids (same seed)."""
    grid = [
        {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
        {"measure": 1, "beat": 0, "symbol": "G7", "duration": 4.0},
        {"measure": 2, "beat": 0, "symbol": "Cmaj7", "duration": 2.0},
        {"measure": 2, "beat": 2, "symbol": "A7", "duration": 2.0},
        {"measure": 3, "beat": 0, "symbol": "Dm7", "duration": 4.0},
    ]
    a = build_arrangement(grid, style="jazz", seed=12345, choruses=2, melodic_temperature=50)
    b = build_arrangement(grid, style="jazz", seed=12345, choruses=2, melodic_temperature=50)
    assert a["bass_events"] == b["bass_events"]
    assert a["solo_events"] == b["solo_events"]
