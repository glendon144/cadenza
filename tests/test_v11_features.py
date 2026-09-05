import pytest
pytest.importorskip("midiutil")
from music.midi_builder import build_arrangement
from music.import_export import dumps_project, loads_project
from render.notation import build_lilypond_source_from_arrangement


def test_choruses_repeat_form_and_make_new_solo_each_chorus():
    grid = [
        {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
        {"measure": 1, "beat": 0, "symbol": "G7", "duration": 4.0},
        {"measure": 2, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
        {"measure": 3, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
    ]
    arr = build_arrangement(grid, style="jazz", seed=99, choruses=3)
    assert arr["choruses"] == 3
    assert arr["total_beats"] == 48
    assert max(c["measure"] for c in arr["chord_cells"]) == 11
    assert any(e["start"] >= 16 for e in arr["solo_events"])
    first = [e["pitch"] for e in arr["solo_events"] if 0 <= e["start"] < 16]
    second = [e["pitch"] for e in arr["solo_events"] if 16 <= e["start"] < 32]
    assert first != second


def test_lilypond_source_ends_with_double_bar():
    grid = [{"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0}]
    arr = build_arrangement(grid, style="jazz", seed=1, choruses=1)
    ly = build_lilypond_source_from_arrangement(arr, 120, title="Ending", chord_cells=arr["chord_cells"], key_sig="C")
    assert '\\bar "|."' in ly


def test_project_round_trip_includes_choruses_and_scale_focus():
    text = dumps_project(
        {"title": "Blue Test", "tempo": 140, "key_sig": "F", "style": "bossa", "groove": "rumba_3_2"},
        [{"measure": 0, "beat": 0, "symbol": "Fmaj7", "duration": 4.0}],
        measures=12,
        choruses=4,
        scale_focus=True,
    )
    data = loads_project(text)
    assert data["format"] == "chordcraft.song"
    assert data["song"]["choruses"] == 4
    assert data["song"]["scale_focus"] is True
    assert data["chords"][0]["symbol"] == "Fmaj7"
