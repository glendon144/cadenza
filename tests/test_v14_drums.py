import pytest
from music.drums import generate_drum_track, KICK, RIDE, CROSS_STICK, CLOSED_HAT


def test_drum_track_is_generated_for_jazz():
    events = generate_drum_track(2, style="jazz", seed=7)
    pitches = {e["pitch"] for e in events}
    assert RIDE in pitches
    assert KICK in pitches
    assert events[-1]["start"] < 8


def test_latin_drums_include_clave_and_hat_texture():
    events = generate_drum_track(2, style="bossa", groove="rumba_3_2", seed=1)
    pitches = {e["pitch"] for e in events}
    assert CROSS_STICK in pitches
    assert CLOSED_HAT in pitches
    assert KICK in pitches


def test_arrangement_contains_drum_events_and_drums_view():
    pytest.importorskip("midiutil")
    from music.midi_builder import build_arrangement
    from render.notation import build_lilypond_source_from_arrangement
    chords = [{"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0}]
    arrangement = build_arrangement(chords, style="jazz", seed=3)
    assert arrangement["drum_events"]
    ly = build_lilypond_source_from_arrangement(arrangement, tempo=140, title="Drum Test", chord_cells=arrangement["chord_cells"], view="drums")
    assert "Drum Part" in ly
    assert "\\new DrumStaff" in ly
    assert "\\drummode" in ly
