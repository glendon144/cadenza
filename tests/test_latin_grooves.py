from music.bassline import generate_bassline
from music.groove import clave_offsets_for_measure, normalize_groove


def test_bossa_bass_uses_dotted_quarter_eighth_root_fifth_pattern():
    events = generate_bassline([{"symbol": "Cmaj7", "duration": 4.0}], style="bossa", seed=1)
    starts = [round(e["start"], 2) for e in events]
    durations = [round(e["duration"], 2) for e in events]
    intervals = [e["pitch"] - events[0]["pitch"] for e in events]
    assert starts == [0.0, 1.5, 2.0, 3.5]
    assert durations == [1.45, 0.42, 1.45, 0.42]
    assert intervals == [0, 0, 7, 7]


def test_bossa_and_samba_default_to_opposite_clave_directions():
    assert normalize_groove("auto", "bossa") == "clave_3_2"
    assert normalize_groove("auto", "samba") == "clave_2_3"
    assert clave_offsets_for_measure(0, "auto", "bossa") == [0.0, 1.5, 3.0]
    assert clave_offsets_for_measure(0, "auto", "samba") == [1.0, 2.5]


def test_latin_arrangement_has_syncopated_comping_not_sustained_whole_notes():
    import pytest
    pytest.importorskip("midiutil")
    from music.midi_builder import build_arrangement

    grid = [{"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0}]
    arrangement = build_arrangement(grid, style="bossa", groove="clave_3_2")
    starts = sorted({round(e["start"], 2) for e in arrangement["chord_events"]})
    durations = sorted({round(e["duration"], 2) for e in arrangement["chord_events"]})
    assert starts == [0.0, 1.5, 3.0]
    assert durations == [0.55]
