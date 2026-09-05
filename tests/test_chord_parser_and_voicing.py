from music.chord_parser import validate_chord_symbol, parse_chord, chord_scale_notes
from music.voicing import voice_chord


def assert_valid(symbol):
    ok, reason = validate_chord_symbol(symbol)
    assert ok, f"{symbol} should validate: {reason}"


def test_common_jazz_symbols_validate():
    for symbol in ["Cmaj7", "CΔ7", "C-7", "Am7b5", "Bø", "G7b9", "Db13", "F7alt", "C/E"]:
        assert_valid(symbol)


def test_major_six_is_a_sixth_not_a_minor_seventh():
    notes = parse_chord("C6", octave=4)
    assert 69 in notes  # A
    assert 70 not in notes  # Bb


def test_jazz_shell_contains_third_and_seventh_for_cmaj7():
    voiced = voice_chord("Cmaj7", style="jazz")
    pcs = {n % 12 for n in voiced["right"]}
    assert 4 in pcs   # E, the 3rd
    assert 11 in pcs  # B, the maj7
    assert 7 not in pcs  # G is less essential than the 7th in the rootless shell


def test_sus_after_extension_replaces_third():
    for symbol in ["G7sus4", "G7sus", "C9sus4", "Bb13sus4", "D7sus2"]:
        assert_valid(symbol)
    notes = {n % 12 for n in parse_chord("G7sus4", octave=4)}
    assert 0 in notes       # C, the 4th over G
    assert 11 not in notes  # B, the 3rd, is replaced
    assert 5 in notes       # F, the b7 stays
    notes = {n % 12 for n in parse_chord("D7sus2", octave=4)}
    assert 4 in notes       # E, the 2nd over D
    assert 6 not in notes   # F#, the 3rd, is replaced


def test_six_nine_chords():
    for symbol in ["C6/9", "C69", "Cm6/9", "F6/9/A"]:
        assert_valid(symbol)
    notes = {n % 12 for n in parse_chord("C6/9", octave=4)}
    assert notes == {0, 4, 7, 9, 2}  # C E G A D
    minor = {n % 12 for n in parse_chord("Cm6/9", octave=4)}
    assert 3 in minor and 9 in minor and 2 in minor
    # A real slash bass after the 6/9 still parses.
    from music.chord_parser import parse_chord_details
    parsed, error = parse_chord_details("F6/9/A")
    assert error is None and parsed.bass == "A"


def test_minor_dash_gets_minor_scale_material():
    pcs = {n % 12 for n in chord_scale_notes("C-7", octave=4)}
    assert 3 in pcs
    assert 10 in pcs
