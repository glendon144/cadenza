import pytest

from music.rms_phrasing import warp_solo_events
from music.import_export import dumps_project, loads_project, FORMAT_VERSION


def test_rms_phrasing_warps_middle_notes_but_preserves_phrase_end():
    events = [
        {"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 80},
        {"pitch": 62, "start": 0.5, "duration": 0.5, "velocity": 80},
        {"pitch": 64, "start": 1.0, "duration": 0.5, "velocity": 80},
        {"pitch": 65, "start": 1.5, "duration": 0.5, "velocity": 80},
    ]
    warped = warp_solo_events(events, tempo=120)
    assert warped[0]["start"] == events[0]["start"]
    assert warped[1]["start"] > events[1]["start"]
    phrase_end = max(e["start"] + e["duration"] for e in events)
    warped_end = max(e["start"] + e["duration"] for e in warped)
    assert warped_end <= phrase_end + 1e-6
    assert all(e.get("rms_phrased") for e in warped)


def test_arrangement_carries_rms_phrasing_flag():
    midi_builder = pytest.importorskip("music.midi_builder")
    arr = midi_builder.build_arrangement([
        {"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
        {"measure": 1, "beat": 0, "symbol": "Dm7", "duration": 4.0},
    ], style="jazz", rms_phrasing=True)
    assert arr["rms_phrasing"] is True


def test_project_json_v3_preserves_rms_phrasing():
    text = dumps_project({"title": "Rubato Test", "style": "jazz"}, [], rms_phrasing=True)
    project = loads_project(text)
    assert FORMAT_VERSION >= 3
    assert project["song"]["rms_phrasing"] is True
