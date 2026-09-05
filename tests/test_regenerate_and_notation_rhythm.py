from render.notation import ly_duration
from music.improv import generate_solo


def test_lilypond_duration_mapping_uses_quarter_note_beats():
    assert ly_duration(0.5) == "8"
    assert ly_duration(0.75) == "8."
    assert ly_duration(1.0) == "4"
    assert ly_duration(1.5) == "4."
    assert ly_duration(2.0) == "2"
    assert ly_duration(3.0) == "2."
    assert ly_duration(4.0) == "1"


def test_regenerate_seed_changes_melody_but_same_seed_is_repeatable():
    seq = [
        {"symbol": "Cmaj7", "duration": 4.0},
        {"symbol": "Am7", "duration": 4.0},
        {"symbol": "Dm7", "duration": 4.0},
        {"symbol": "G7", "duration": 4.0},
    ]
    a = generate_solo(seq, style="bossa", seed=101)
    b = generate_solo(seq, style="bossa", seed=101)
    c = generate_solo(seq, style="bossa", seed=202)
    assert a == b
    assert a != c


def test_generated_melody_prefers_small_intervals():
    seq = [{"symbol": s, "duration": 4.0} for s in ["Cmaj7", "Am7", "Dm7", "G7"] * 2]
    solo = generate_solo(seq, style="bossa", seed=303)
    intervals = [abs(b["pitch"] - a["pitch"]) for a, b in zip(solo, solo[1:])]
    assert intervals
    small = [i for i in intervals if i <= 5]
    assert len(small) / len(intervals) >= 0.75
