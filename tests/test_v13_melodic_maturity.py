import pytest
from music.improv import generate_solo
from music.import_export import dumps_project, loads_project


def _ii_v_i():
    return [
        {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
        {"measure": 1, "beat": 0, "symbol": "G7", "duration": 4.0},
        {"measure": 2, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
        {"measure": 3, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
    ]


def test_high_melodic_temperature_adds_motive_metadata():
    solo = generate_solo(
        [{"symbol": c["symbol"], "duration": c["duration"]} for c in _ii_v_i()],
        style="jazz",
        seed=44,
        scale_focus=True,
        melodic_temperature=95,
    )
    assert any(e.get("motive_id") for e in solo)


def test_high_melodic_temperature_can_generate_enclosures():
    found = False
    for seed in range(20, 40):
        solo = generate_solo(
            [{"symbol": c["symbol"], "duration": c["duration"]} for c in _ii_v_i()],
            style="jazz",
            seed=seed,
            scale_focus=True,
            melodic_temperature=100,
        )
        if any(e.get("enclosure") for e in solo):
            found = True
            break
    assert found


def test_arrangement_reports_phrase_metadata():
    pytest.importorskip("midiutil")
    from music.midi_builder import build_arrangement
    arrangement = build_arrangement(_ii_v_i(), style="jazz", seed=44, scale_focus=True, choruses=2, melodic_temperature=95)
    meta = arrangement["phrase_metadata"]
    assert meta["motive_event_count"] > 0
    assert arrangement["melodic_temperature"] == 95


def test_project_json_round_trips_melodic_temperature():
    text = dumps_project(
        {"title": "Motivic Blues", "tempo": 140, "key_sig": "F", "style": "jazz", "groove": "auto"},
        _ii_v_i(),
        measures=12,
        choruses=3,
        scale_focus=True,
        melodic_temperature=82,
    )
    project = loads_project(text)
    assert project["song"]["melodic_temperature"] == 82
    assert project["version"] >= 2
