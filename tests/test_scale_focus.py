import pytest
from music.scale_syllabus import scale_choices, scale_focus_notes
from music.improv import generate_solo


def pitch_classes(events):
    return {int(e['pitch']) % 12 for e in events if 'pitch' in e}


def test_scale_choices_contain_basic_chord_tones():
    choices = scale_choices('G7')
    assert choices
    # G B D F must appear in every dominant choice.
    chord_tones = {7, 11, 2, 5}
    assert all(chord_tones.issubset(set(pcs)) for _name, pcs in choices)


def test_scale_focus_notes_include_aebersold_dominant_material():
    pcs = {n % 12 for n in scale_focus_notes('G7', octave=4)}
    # Mixolydian on G: G A B C D E F.
    assert {7, 9, 11, 0, 2, 4, 5}.issubset(pcs)


def test_scale_focus_solo_uses_more_than_chord_tones():
    seq = [{'symbol': 'G7', 'duration': 8.0}]
    solo = generate_solo(seq, style='jazz', seed=44, scale_focus=True)
    pcs = pitch_classes(solo)
    chord_tones = {7, 11, 2, 5}
    assert pcs - chord_tones


def test_arrangement_marks_scale_focus_and_still_builds():
    pytest.importorskip('midiutil')
    from music.midi_builder import build_arrangement
    grid = [{'measure': 0, 'beat': 0, 'symbol': 'Dm7', 'duration': 4.0}, {'measure': 1, 'beat': 0, 'symbol': 'G7', 'duration': 4.0}]
    arr = build_arrangement(grid, style='jazz', seed=12, scale_focus=True)
    assert arr['scale_focus'] is True
    assert arr['solo_events']
    assert arr['bass_events']
