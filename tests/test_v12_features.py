from render.notation import build_lilypond_source_from_arrangement


def sample_arrangement():
    return {
        "chord_events": [
            {"pitch": 60, "start": 0.0, "duration": 4.0, "velocity": 70},
            {"pitch": 64, "start": 0.0, "duration": 4.0, "velocity": 70},
            {"pitch": 67, "start": 0.0, "duration": 4.0, "velocity": 70},
            {"pitch": 48, "start": 0.0, "duration": 4.0, "velocity": 64},
        ],
        "bass_events": [{"pitch": 36, "start": 0.0, "duration": 1.0, "velocity": 76}],
        "solo_events": [{"pitch": 72, "start": 0.5, "duration": 0.5, "velocity": 84}],
        "total_beats": 8.0,
    }


def test_part_view_subtitles_and_staff_counts():
    cells = [{"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0}]
    solo = build_lilypond_source_from_arrangement(sample_arrangement(), 180, "Part Test", cells, "C", view="solo")
    bass = build_lilypond_source_from_arrangement(sample_arrangement(), 180, "Part Test", cells, "C", view="bass")
    rhythm = build_lilypond_source_from_arrangement(sample_arrangement(), 180, "Part Test", cells, "C", view="rhythm")
    full = build_lilypond_source_from_arrangement(sample_arrangement(), 180, "Part Test", cells, "C", view="full")

    assert 'subtitle = "Solo Part"' in solo
    assert '\\with { instrumentName = "Solo" }' in solo
    assert 'subtitle = "Bass Part"' in bass
    assert '\\with { instrumentName = "Bass" }' in bass
    assert 'subtitle = "Rhythm Part"' in rhythm
    assert 'instrumentName = "Rhythm"' in rhythm
    assert 'subtitle = "Full Score"' in full
    assert 'instrumentName = "Piano"' in full


def test_unknown_part_view_falls_back_to_full_score():
    ly = build_lilypond_source_from_arrangement(sample_arrangement(), 120, "Fallback", [], "C", view="nonsense")
    assert 'subtitle = "Full Score"' in ly
