from pathlib import Path

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    import database.db as db
    import app as app_module

    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    app_module.app.config["TESTING"] = True
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready
    with app_module.app.test_client() as test_client:
        yield test_client
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready


def test_audio_mode_defaults_to_current_and_selects_managed_soundfont(tmp_path, monkeypatch):
    import render.audio as audio

    managed = tmp_path / "GeneralUser-GS.sf2"
    managed.write_bytes(b"soundfont")
    monkeypatch.setattr(audio, "MANAGED_SOUNDFONT_PATH", managed)
    monkeypatch.setattr(audio, "SOUNDFONT_PATH", "/system/current.sf2")

    assert audio.normalize_audio_mode(None) == "current"
    assert audio.soundfont_for_mode(None) == "/system/current.sf2"
    assert audio.soundfont_for_mode("soundfont") == str(managed)


def test_midi_to_wav_uses_selected_soundfont(tmp_path, monkeypatch):
    import render.audio as audio

    managed = tmp_path / "GeneralUser-GS.sf2"
    managed.write_bytes(b"soundfont")
    monkeypatch.setattr(audio, "MANAGED_SOUNDFONT_PATH", managed)
    monkeypatch.setattr(audio, "require_dependencies", lambda **kwargs: None)
    commands = []

    class Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(audio.subprocess, "run", lambda command, **kwargs: commands.append(command) or Result())
    midi = tmp_path / "song.mid"
    wav = tmp_path / "song.wav"

    audio.midi_to_wav(midi, wav, audio_mode="soundfont")

    assert commands[0][-2] == str(managed)
    assert commands[0][-1] == str(midi)


def test_download_soundfont_writes_an_atomic_managed_file(tmp_path, monkeypatch):
    import render.audio as audio

    class FakeResponse:
        def __init__(self):
            self.read_once = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            if self.read_once:
                self.read_once = False
                return b"open-source-sf2"
            return b""

    monkeypatch.setattr(audio, "urlopen", lambda url, timeout: FakeResponse())
    target = tmp_path / "soundfonts" / "GeneralUser-GS.sf2"

    assert audio.download_soundfont(target, "https://example.test/GeneralUser-GS.sf2") == str(target)
    assert target.read_bytes() == b"open-source-sf2"
    assert not Path(str(target) + ".download").exists()


def test_soundfont_download_requires_explicit_consent(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "managed_soundfont_available", lambda: False)
    response = client.post("/api/audio/soundfont", json={})
    assert response.status_code == 403

    downloaded = "/tmp/GeneralUser-GS.sf2"
    monkeypatch.setattr(app_module, "download_soundfont", lambda: downloaded)
    response = client.post("/api/audio/soundfont", json={"consent": True})
    assert response.status_code == 200
    assert response.get_json() == {"available": True, "ok": True, "path": downloaded}


def test_audio_mode_is_exposed_in_render_payload_and_ui():
    js = open("static/js/app.js", encoding="utf-8").read()
    html = open("templates/index.html", encoding="utf-8").read()

    assert 'audio_mode: state.settings.audio_mode' in js
    assert '"/api/audio/soundfont"' in js
    assert 'id="audio-mode"' in html
    assert 'value="current" selected' in html
    assert 'value="soundfont"' in html
