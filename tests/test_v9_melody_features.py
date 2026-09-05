from music.chord_parser import is_dominant_chord, tritone_sub_symbol
from music.bassline import generate_bassline
from music.improv import generate_solo
from render.notation import chord_symbols_to_ly, events_to_ly_voice


def test_dominant_tritone_sub_symbol():
    assert is_dominant_chord("G7")
    assert tritone_sub_symbol("G7") == "Db7"
    assert tritone_sub_symbol("G7alt") == "Db7alt"
    assert not is_dominant_chord("Cmaj7")
    assert tritone_sub_symbol("Cmaj7") is None


def test_bass_can_use_tritone_sub_for_downward_half_step_resolution():
    seq = [
        {"symbol": "Dm7", "duration": 4.0},
        {"symbol": "G7", "duration": 4.0},
        {"symbol": "Cmaj7", "duration": 4.0},
    ]
    events = generate_bassline(seq, style="jazz", seed=1)
    g7_bar = [e for e in events if 4.0 <= e["start"] < 8.0]
    # Db in bass octave is MIDI 37, the tritone substitute root resolving to C.
    assert any(e["pitch"] == 37 for e in g7_bar)


def test_solo_generates_complete_triplet_groups_and_notates_them():
    seq = [{"symbol": "Dm7", "duration": 4.0}] * 4
    events = generate_solo(seq, style="jazz", seed=3)
    triplets = [e for e in events if e.get("tuplet") == "triplet"]
    assert triplets
    group_ids = {e["tuplet_group"] for e in triplets}
    # Every sounding triplet event carries slot/unit metadata so rests can fill
    # the remaining triplet slots in LilyPond.
    assert all("tuplet_slot" in e and "tuplet_unit" in e for e in triplets)
    ly = events_to_ly_voice(events, total_beats=16.0, tempo=120, key_sig="C")
    assert "\\tuplet 3/2" in ly
    assert group_ids


def test_chord_symbols_render_two_slots_per_bar():
    ly = chord_symbols_to_ly([
        {"measure": 0, "beat": 0, "symbol": "Dm7"},
        {"measure": 0, "beat": 2, "symbol": "G7"},
    ], total_beats=4.0)
    assert 's2^\\markup \\bold "Dm7"' in ly
    assert 's2^\\markup \\bold "G7"' in ly
