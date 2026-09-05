"""Tests for v17 stem rendering: per-part audio for live browser mixing."""

import pytest

pytest.importorskip("midiutil")

from music.midi_builder import MIXER_TRACKS, build_arrangement, mixer_levels, stem_mixer, write_midi


GRID = [
    {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
    {"measure": 1, "beat": 0, "symbol": "G7", "duration": 4.0},
    {"measure": 2, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
]


def _instruments(path):
    pretty_midi = pytest.importorskip("pretty_midi")
    midi = pretty_midi.PrettyMIDI(str(path))
    by_role = {}
    for inst in midi.instruments:
        if inst.is_drum:
            by_role["drums"] = inst
        elif inst.program == 32:
            by_role["bass"] = inst
        elif inst.program == 56:
            by_role["solo"] = inst
        else:
            by_role["rhythm"] = inst
    return by_role


# ── stem_mixer ───────────────────────────────────────────────────────────────

def test_stem_mixer_isolates_one_part_at_full_volume():
    for part in MIXER_TRACKS:
        levels = mixer_levels(stem_mixer(part))
        assert levels[part]["include"] is True
        assert levels[part]["cc7"] == 127
        for other in MIXER_TRACKS:
            if other != part:
                assert levels[other]["include"] is False
                assert levels[other]["cc7"] == 0


def test_stem_mixer_rejects_unknown_part():
    with pytest.raises(ValueError):
        stem_mixer("kazoo")


def test_stem_midi_contains_only_its_part(tmp_path):
    arr = build_arrangement(GRID, style="jazz", seed=11)
    for part in MIXER_TRACKS:
        path = write_midi(arr, tempo=140, output_path=tmp_path / f"{part}.mid", mixer=stem_mixer(part))
        parts = _instruments(path)
        assert len(parts[part].notes) > 0
        for other, inst in parts.items():
            if other != part:
                assert len(inst.notes) == 0


def test_stems_from_same_arrangement_share_length(tmp_path):
    pretty_midi = pytest.importorskip("pretty_midi")
    arr = build_arrangement(GRID, style="jazz", seed=11)
    # Stems must stay in sync when layered: none may outrun the full mix.
    full = write_midi(arr, tempo=140, output_path=tmp_path / "full.mid", mixer=None)
    full_end = pretty_midi.PrettyMIDI(str(full)).get_end_time()
    for part in MIXER_TRACKS:
        path = write_midi(arr, tempo=140, output_path=tmp_path / f"{part}.mid", mixer=stem_mixer(part))
        assert pretty_midi.PrettyMIDI(str(path)).get_end_time() <= full_end + 0.01


# ── Render API ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    import database.db as db
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    import app as app_module
    app_module.app.config["TESTING"] = True
    monkeypatch.setattr(app_module, "EXPORT_DIR", tmp_path / "exports")

    def fake_render_audio(midi_path, wav_path=None, mp3_path=None):
        from pathlib import Path
        mp3 = Path(mp3_path if mp3_path else Path(midi_path).with_suffix(".mp3"))
        mp3.write_bytes(b"mp3")
        return {"wav": str(wav_path or mp3.with_suffix(".wav")), "mp3": str(mp3)}

    def fake_render_svgs(source, output_stem, output_dir):
        from pathlib import Path
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
        yield c
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready


CHORDS = [{"measure": 0, "beat": 0, "symbol": "Cmaj7", "duration": 4.0}]


def test_render_returns_stems_when_requested(client):
    song_id = client.post("/api/songs", json={"title": "Stems"}).get_json()["id"]
    resp = client.post(f"/api/songs/{song_id}/render", json={"chords": CHORDS, "stems": True})
    assert resp.status_code == 200
    stems = resp.get_json()["stem_urls"]
    assert set(stems) == set(MIXER_TRACKS)
    for url in stems.values():
        assert url.endswith(".mp3")


def test_render_skips_stems_by_default(client):
    song_id = client.post("/api/songs", json={"title": "No Stems"}).get_json()["id"]
    resp = client.post(f"/api/songs/{song_id}/render", json={"chords": CHORDS})
    assert resp.status_code == 200
    assert resp.get_json()["stem_urls"] is None
