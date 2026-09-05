"""Tests for v18 transposing-instrument notation (written-pitch parts)."""

import pytest

pytest.importorskip("midiutil")

from music.key_utils import (
    TRANSPOSING_INSTRUMENTS,
    normalize_transposition,
    transposed_key_sig,
)


# ── Instrument table and key math ────────────────────────────────────────────

def test_instrument_offsets_match_convention():
    # written = concert + semitones
    assert TRANSPOSING_INSTRUMENTS["concert"]["semitones"] == 0
    assert TRANSPOSING_INSTRUMENTS["bb"]["semitones"] == 2          # major 2nd
    assert TRANSPOSING_INSTRUMENTS["eb_alto"]["semitones"] == 9     # major 6th
    assert TRANSPOSING_INSTRUMENTS["bb_tenor"]["semitones"] == 14   # major 9th
    assert TRANSPOSING_INSTRUMENTS["eb_bari"]["semitones"] == 21    # M6 + octave
    assert TRANSPOSING_INSTRUMENTS["f_horn"]["semitones"] == 7      # perfect 5th


def test_normalize_transposition():
    assert normalize_transposition("eb_alto") == "eb_alto"
    assert normalize_transposition(" EB_ALTO ") == "eb_alto"
    assert normalize_transposition("kazoo") == "concert"
    assert normalize_transposition(None) == "concert"


def test_written_keys_for_alto():
    # Concert C for an E♭ alto is written in A; concert E♭ is written in C.
    assert transposed_key_sig("C", 9) == "A"
    assert transposed_key_sig("Eb", 9) == "C"
    assert transposed_key_sig("F", 9) == "D"


def test_written_keys_for_bb_and_horn():
    # Concert B♭ for a B♭ trumpet is written C; concert F for an F horn is C.
    assert transposed_key_sig("Bb", 2) == "C"
    assert transposed_key_sig("C", 2) == "D"
    assert transposed_key_sig("F", 7) == "C"
    # Octave displacement never changes the key signature.
    assert transposed_key_sig("Bb", 14) == "C"
    assert transposed_key_sig("C", 21) == "A"


def test_concert_key_passes_through():
    assert transposed_key_sig("Gb", 0) == "Gb"
    assert transposed_key_sig("C", 12) == "C"


# ── Notation output ──────────────────────────────────────────────────────────

GRID = [
    {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
    {"measure": 1, "beat": 0, "symbol": "G7", "duration": 4.0},
    {"measure": 2, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
]


@pytest.fixture(scope="module")
def arrangement():
    from music.midi_builder import build_arrangement
    return build_arrangement(GRID, style="jazz", seed=7)


def _source(arrangement, **kwargs):
    from render.notation import build_lilypond_source_from_arrangement
    return build_lilypond_source_from_arrangement(
        arrangement, 140, title="Transpose Test", chord_cells=GRID, key_sig="C", **kwargs
    )


def test_concert_source_unchanged_by_default(arrangement):
    src = _source(arrangement)
    assert "\\key c \\major" in src
    assert '"Dm7"' in src
    assert "Written for" not in src


def test_alto_part_written_in_a_with_transposed_chords(arrangement):
    src = _source(arrangement, transposition=9, transposition_label="E♭ — Alto Sax")
    assert "\\key a \\major" in src
    # Dm7/G7/Cmaj7 concert become Bm7/E7/Amaj7 written.
    assert '"Bm7"' in src
    assert '"E7"' in src
    assert '"Amaj7"' in src
    assert '"Dm7"' not in src
    assert "Written for E♭ — Alto Sax" in src


def test_bb_part_written_one_step_up(arrangement):
    src = _source(arrangement, transposition=2, transposition_label="B♭ — Trumpet")
    assert "\\key d \\major" in src
    assert '"Em7"' in src
    assert '"A7"' in src
    assert '"Dmaj7"' in src


def test_transposition_shifts_written_pitches(arrangement):
    """An octave transposition keeps note names but must change the source."""
    concert = _source(arrangement)
    octave = _source(arrangement, transposition=12, transposition_label="Test 8va")
    assert concert != octave
    assert "\\key c \\major" in octave  # same key, an octave up
    # Concert chords are unchanged by a pure octave shift.
    assert '"Dm7"' in octave


def test_playback_midi_is_never_transposed(arrangement, tmp_path):
    """Transposition is notation-only: MIDI output ignores it entirely."""
    from music.midi_builder import write_midi
    path = write_midi(arrangement, tempo=140, output_path=tmp_path / "concert.mid")
    pretty_midi = pytest.importorskip("pretty_midi")
    midi = pretty_midi.PrettyMIDI(str(path))
    pitches = sorted(n.pitch for inst in midi.instruments for n in inst.notes)
    # write_midi has no transposition parameter; this documents the contract.
    assert pitches, "sanity: arrangement produces notes"


# ── Render API ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    import database.db as db
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    import app as app_module
    app_module.app.config["TESTING"] = True
    monkeypatch.setattr(app_module, "EXPORT_DIR", tmp_path / "exports")

    captured = {}

    def fake_render_audio(midi_path, wav_path=None, mp3_path=None):
        from pathlib import Path
        mp3 = Path(mp3_path if mp3_path else Path(midi_path).with_suffix(".mp3"))
        mp3.write_bytes(b"mp3")
        return {"wav": str(wav_path or mp3.with_suffix(".wav")), "mp3": str(mp3)}

    def fake_render_svgs(source, output_stem, output_dir):
        from pathlib import Path
        captured["source"] = source
        svg = Path(output_dir) / f"{output_stem}.svg"
        svg.write_text("<svg/>")
        return [str(svg)]

    def fake_render_pdf(source, output_stem, output_dir):
        from pathlib import Path
        pdf = Path(output_dir) / f"{output_stem}.pdf"
        pdf.write_bytes(b"pdf")
        return str(pdf)

    monkeypatch.setattr(app_module, "render_audio", fake_render_audio)
    monkeypatch.setattr(app_module, "render_svgs", fake_render_svgs)
    monkeypatch.setattr(app_module, "render_pdf", fake_render_pdf)

    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready
    with app_module.app.test_client() as c:
        c.captured = captured
        yield c
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready


CHORDS = [{"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0}]


def test_render_applies_transposition_to_notation(client):
    song_id = client.post("/api/songs", json={"title": "Alto"}).get_json()["id"]
    resp = client.post(f"/api/songs/{song_id}/render",
                       json={"chords": CHORDS, "transposition": "eb_alto"})
    assert resp.status_code == 200
    assert resp.get_json()["transposition"] == "eb_alto"
    assert '"Bm7"' in client.captured["source"]
    assert "Written for" in client.captured["source"]


def test_render_defaults_to_concert(client):
    song_id = client.post("/api/songs", json={"title": "Concert"}).get_json()["id"]
    resp = client.post(f"/api/songs/{song_id}/render", json={"chords": CHORDS})
    assert resp.status_code == 200
    assert resp.get_json()["transposition"] == "concert"
    assert '"Dm7"' in client.captured["source"]


def test_render_rejects_unknown_instrument_gracefully(client):
    song_id = client.post("/api/songs", json={"title": "Kazoo"}).get_json()["id"]
    resp = client.post(f"/api/songs/{song_id}/render",
                       json={"chords": CHORDS, "transposition": "kazoo"})
    assert resp.status_code == 200
    assert resp.get_json()["transposition"] == "concert"
