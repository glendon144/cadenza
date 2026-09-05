import json
from io import BytesIO

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


PROJECT = {
    "title": "My Current Name",
    "tempo": 132,
    "style": "jazz",
    "key_sig": "Bb",
    "groove": "auto",
    "measures": 4,
    "choruses": 2,
    "scale_focus": True,
    "rms_phrasing": True,
    "melodic_temperature": 68,
    "chords": [
        {"measure": 0, "beat": 0, "symbol": "Bbmaj7", "duration": 4},
        {"measure": 1, "beat": 0, "symbol": "Eb7", "duration": 4},
    ],
}


def test_project_export_uses_current_project_name_and_chords(client):
    response = client.post("/api/project/export", json=PROJECT)

    assert response.status_code == 200
    assert "My_Current_Name-jazz" in response.headers["Content-Disposition"]
    exported = json.loads(response.get_data(as_text=True))
    assert exported["song"]["title"] == PROJECT["title"]
    assert exported["chords"] == PROJECT["chords"]


def test_project_import_returns_normalized_project_for_frontend(client):
    response = client.post(
        "/api/project/import",
        data={
            "file": (BytesIO(json.dumps(PROJECT).encode("utf-8")), "My Current Name.chordcraft.json"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    imported = response.get_json()
    assert imported["song"]["title"] == PROJECT["title"]
    assert imported["song"]["measures"] == 4
    assert [chord["symbol"] for chord in imported["chords"]] == ["Bbmaj7", "Eb7"]


def test_project_import_rejects_missing_file(client):
    response = client.post("/api/project/import")

    assert response.status_code == 400
    assert "No file uploaded" in response.get_json()["error"]


def test_frontend_uses_full_project_payload_for_file_workflows():
    source = open("static/js/app.js", encoding="utf-8").read()

    assert "body: JSON.stringify(currentProjectPayload())" in source
    assert "await createSongFromProject(data);" in source
    assert "body: JSON.stringify({ song_id: currentSongId() })" not in source
    for field in ("title", "tempo", "style", "key_sig"):
        assert f"{field}: song{ {'title': 'Title', 'tempo': 'Tempo', 'style': 'Style', 'key_sig': 'Key'}[field] }.value" in source
    assert "scheduleMixerSave();" in source
    assert "{ mixer: state.settings.mixer }" in source
