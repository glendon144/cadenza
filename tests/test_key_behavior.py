from music.key_utils import diatonic_seventh_chords, key_delta_semitones, transpose_chord_symbol
from render.notation import midi_note_to_ly


def test_diatonic_seventh_chords_in_f_major():
    assert diatonic_seventh_chords("F") == ["Fmaj7", "Gm7", "Am7", "Bbmaj7", "C7", "Dm7", "Em7b5"]


def test_transpose_c_to_f_preserves_chord_quality_and_slash_bass():
    delta = key_delta_semitones("C", "F")
    assert transpose_chord_symbol("Cmaj7", delta, "F") == "Fmaj7"
    assert transpose_chord_symbol("Am7b5/Eb", delta, "F") == "Dm7b5/Ab"


def test_lilypond_prefers_flat_spelling_in_flat_keys():
    assert midi_note_to_ly(70, "F") == "bes'"
