"""Tests for the v16 mixer: per-part volume, Active, Solo, and Mute."""

import pytest

pytest.importorskip("midiutil")

from music.midi_builder import MIXER_TRACKS, build_arrangement, mixer_levels, write_midi


def _strip(**overrides):
    base = {"active": True, "mute": False, "solo": False, "volume": 80}
    base.update(overrides)
    return base


# ── Level resolution ─────────────────────────────────────────────────────────

def test_default_levels_include_everything():
    levels = mixer_levels({})
    for name in MIXER_TRACKS:
        assert levels[name]["include"] is True
        assert levels[name]["cc7"] == round(80 * 127 / 100)


def test_volume_maps_to_cc7():
    levels = mixer_levels({"bass": _strip(volume=100), "drums": _strip(volume=0)})
    assert levels["bass"]["cc7"] == 127
    assert levels["drums"]["cc7"] == 0


def test_mute_silences_but_keeps_track():
    levels = mixer_levels({"solo": _strip(mute=True)})
    assert levels["solo"]["cc7"] == 0
    assert levels["solo"]["include"] is True


def test_solo_silences_other_tracks():
    levels = mixer_levels({"bass": _strip(solo=True)})
    assert levels["bass"]["cc7"] > 0
    for name in ("rhythm", "solo", "drums"):
        assert levels[name]["cc7"] == 0
        assert levels[name]["include"] is True


def test_two_solos_both_audible():
    levels = mixer_levels({"bass": _strip(solo=True), "drums": _strip(solo=True)})
    assert levels["bass"]["cc7"] > 0
    assert levels["drums"]["cc7"] > 0
    assert levels["rhythm"]["cc7"] == 0


def test_inactive_channel_is_excluded():
    levels = mixer_levels({"drums": _strip(active=False)})
    assert levels["drums"]["include"] is False
    assert levels["drums"]["cc7"] == 0
    # An inactive solo must not gate the other channels.
    levels = mixer_levels({"drums": _strip(active=False, solo=True)})
    assert levels["rhythm"]["cc7"] > 0


def test_all_muted_is_all_silent():
    levels = mixer_levels({name: _strip(mute=True) for name in MIXER_TRACKS})
    assert all(levels[n]["cc7"] == 0 for n in MIXER_TRACKS)
    assert all(levels[n]["include"] for n in MIXER_TRACKS)


def test_bad_values_fall_back_to_defaults():
    levels = mixer_levels({"bass": {"volume": "loud"}, "solo": None})
    assert levels["bass"]["cc7"] == round(80 * 127 / 100)
    assert levels["solo"]["include"] is True


# ── MIDI output ──────────────────────────────────────────────────────────────

GRID = [
    {"measure": 0, "beat": 0, "symbol": "Dm7", "duration": 4.0},
    {"measure": 1, "beat": 0, "symbol": "G7", "duration": 4.0},
    {"measure": 2, "beat": 0, "symbol": "Cmaj7", "duration": 4.0},
]


def _write(tmp_path, mixer, name="mix.mid"):
    arr = build_arrangement(GRID, style="jazz", seed=11)
    return write_midi(arr, tempo=140, output_path=tmp_path / name, mixer=mixer)


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


def _cc7(inst):
    return [c.value for c in inst.control_changes if c.number == 7]


def test_write_midi_without_mixer_has_no_cc7(tmp_path):
    path = _write(tmp_path, mixer=None)
    for inst in _instruments(path).values():
        assert _cc7(inst) == []


def test_write_midi_applies_mixer_volumes(tmp_path):
    path = _write(tmp_path, mixer={"bass": _strip(volume=100), "drums": _strip(mute=True)})
    parts = _instruments(path)
    assert _cc7(parts["bass"]) == [127]
    assert _cc7(parts["drums"]) == [0]
    assert len(parts["drums"].notes) > 0, "muted part must keep its notes"
    assert _cc7(parts["rhythm"]) == [round(80 * 127 / 100)]


def test_all_muted_keeps_full_length_but_silent(tmp_path):
    mixer = {name: _strip(mute=True) for name in MIXER_TRACKS}
    path = _write(tmp_path, mixer=mixer)
    parts = _instruments(path)
    assert len(parts) == 4
    for inst in parts.values():
        assert _cc7(inst) == [0]
        assert len(inst.notes) > 0
    # The silent file still spans the whole form.
    pretty_midi = pytest.importorskip("pretty_midi")
    midi = pretty_midi.PrettyMIDI(str(path))
    assert midi.get_end_time() > 4.0


def test_inactive_part_dropped_from_midi(tmp_path):
    path = _write(tmp_path, mixer={"drums": _strip(active=False)})
    parts = _instruments(path)
    assert "drums" not in parts or len(parts["drums"].notes) == 0
    for name in ("rhythm", "bass", "solo"):
        assert len(parts[name].notes) > 0


# ── Per-song persistence ─────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    import database.db as db
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "test.db")
    import app as app_module
    app_module.app.config["TESTING"] = True
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready
    with app_module.app.test_client() as c:
        yield c
    if hasattr(app_module.app, "_db_ready"):
        del app_module.app._db_ready


def test_mixer_round_trips_through_save_and_load(client):
    song_id = client.post("/api/songs", json={"title": "Mix Persist"}).get_json()["id"]
    mixer = {
        "rhythm": _strip(volume=55),
        "bass": _strip(solo=True),
        "solo": _strip(mute=True),
        "drums": _strip(active=False, volume=30),
    }
    resp = client.put(f"/api/songs/{song_id}", json={"mixer": mixer})
    assert resp.status_code == 200

    data = client.get(f"/api/songs/{song_id}").get_json()
    assert data["mixer"] == mixer


def test_mixer_is_normalized_before_storage(client):
    song_id = client.post("/api/songs", json={}).get_json()["id"]
    client.put(f"/api/songs/{song_id}", json={"mixer": {
        "bass": {"volume": 400, "mute": 1},
        "unknown_track": {"volume": 10},
        "drums": "garbage",
    }})
    data = client.get(f"/api/songs/{song_id}").get_json()
    mixer = data["mixer"]
    assert set(mixer) == set(MIXER_TRACKS)
    assert mixer["bass"]["volume"] == 100
    assert mixer["bass"]["mute"] is True
    assert mixer["drums"] == _strip()
    assert "unknown_track" not in mixer


def test_mixer_defaults_to_null_until_saved(client):
    song_id = client.post("/api/songs", json={}).get_json()["id"]
    data = client.get(f"/api/songs/{song_id}").get_json()
    assert data["mixer"] is None
    # Explicitly clearing also returns null.
    client.put(f"/api/songs/{song_id}", json={"mixer": {"bass": _strip(volume=10)}})
    client.put(f"/api/songs/{song_id}", json={"mixer": None})
    data = client.get(f"/api/songs/{song_id}").get_json()
    assert data["mixer"] is None
