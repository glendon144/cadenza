"""ChordCraft — Flask application entry point."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
import zipfile
from flask import Flask, abort, jsonify, render_template, request, send_file, Response
from werkzeug.utils import safe_join

from config import DEFAULT_STYLE, DEFAULT_TEMPO, EXPORT_DIR, MAX_MEASURES
from database.models import (
    init_db, create_song, get_song, list_songs, update_song, delete_song,
    save_chord_grid, get_chord_grid, save_render, clamp_tempo,
)
from music.chord_parser import validate_chord_symbol
from music.midi_builder import MIXER_TRACKS, build_arrangement, normalize_mixer, stem_mixer, write_midi
from music.groove import normalize_groove, normalize_style
from music.key_utils import TRANSPOSING_INSTRUMENTS, normalize_key, normalize_transposition
from render.audio import render_audio
from render.notation import build_lilypond_source_from_arrangement, render_pdf, render_svgs
from render.preflight import check_dependencies
from render.export_names import export_basename, unique_path
from music.import_export import dumps_project, loads_project, import_midi_to_project
from music.musicxml_import import import_musicxml_to_project
from music.provider_export import load_provider, build_prompt, apply_restraints, list_providers, get_provider_dir

app = Flask(__name__)



def validate_chord_cells(cells):
    invalid = []
    valid = []
    seen = set()
    for raw in cells or []:
        try:
            measure = int(raw.get("measure", 0))
            beat = int(raw.get("beat", 0))
            duration = float(raw.get("duration", 4.0))
        except (TypeError, ValueError):
            invalid.append({"measure": raw.get("measure"), "beat": raw.get("beat", 0), "symbol": raw.get("symbol", ""), "message": "Bad measure, beat, or duration."})
            continue

        symbol = (raw.get("symbol") or "").strip()
        if not symbol:
            continue
        if measure < 0 or measure >= MAX_MEASURES:
            invalid.append({"measure": measure, "beat": beat, "symbol": symbol, "message": f"Measure must be between 1 and {MAX_MEASURES}."})
            continue
        if beat < 0 or beat > 3:
            invalid.append({"measure": measure, "beat": beat, "symbol": symbol, "message": "Beat must be 0 through 3."})
            continue
        if duration <= 0 or duration > 16:
            invalid.append({"measure": measure, "beat": beat, "symbol": symbol, "message": "Duration must be positive and reasonably short."})
            continue

        ok, reason = validate_chord_symbol(symbol)
        if not ok:
            invalid.append({"measure": measure, "beat": beat, "symbol": symbol, "message": reason or "This chord is not recognized."})
            continue

        key = (measure, beat)
        if key not in seen:
            seen.add(key)
            valid.append({"measure": measure, "beat": beat, "symbol": symbol[:40], "duration": duration})

    return valid, invalid


def export_url(path: str | Path) -> str:
    rel = Path(path).resolve().relative_to(EXPORT_DIR.resolve())
    return "/exports/" + rel.as_posix()


@app.before_request
def startup():
    if not hasattr(app, "_db_ready"):
        init_db()
        app._db_ready = True


@app.route("/")
def index():
    return render_template("index.html", songs=list_songs())


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify(check_dependencies())


@app.route("/api/providers", methods=["GET"])
def api_list_providers():
    """List all available provider configs from providers/*.json"""
    try:
        providers = list_providers()
        return jsonify(providers)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/providers/<provider_id>", methods=["GET"])
def api_get_provider(provider_id):
    try:
        provider = load_provider(provider_id)
        return jsonify(provider)
    except FileNotFoundError:
        return jsonify({"error": f"Provider {provider_id} not found"}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/providers/import", methods=["POST"])
def api_import_provider():
    """Import a new provider JSON via file upload - future-proofing"""
    uploaded = request.files.get("file")
    if not uploaded:
        # also support raw JSON body
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "No provider JSON uploaded"}), 400
        provider_data = data
        filename = f"{provider_data.get('provider_id','custom')}.json"
    else:
        try:
            text = uploaded.read().decode("utf-8")
            provider_data = json.loads(text)
            filename = uploaded.filename or f"{provider_data.get('provider_id','custom')}.json"
        except Exception as exc:
            return jsonify({"error": f"Invalid provider JSON: {exc}"}), 400

    # basic validation
    if "provider_id" not in provider_data or "prompt_template" not in provider_data:
        return jsonify({"error": "Provider JSON must have provider_id and prompt_template"}), 400

    try:
        provider_dir = get_provider_dir()
        provider_dir.mkdir(parents=True, exist_ok=True)
        dest = provider_dir / filename
        dest.write_text(json.dumps(provider_data, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "provider_id": provider_data["provider_id"], "file": filename})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500



@app.route("/api/songs", methods=["GET"])
def api_list_songs():
    return jsonify([dict(s) for s in list_songs()])


@app.route("/api/songs", methods=["POST"])
def api_create_song():
    data = request.get_json(silent=True) or {}
    song_id = create_song(
        title=data.get("title", "Untitled"),
        tempo=data.get("tempo", DEFAULT_TEMPO),
        key_sig=normalize_key(data.get("key_sig", "C")),
        style=normalize_style(data.get("style", DEFAULT_STYLE)),
        groove=normalize_groove(data.get("groove", "auto"), data.get("style", DEFAULT_STYLE)),
    )
    return jsonify({"id": song_id}), 201


@app.route("/api/songs/<int:song_id>", methods=["GET"])
def api_get_song(song_id):
    song = get_song(song_id)
    if not song:
        abort(404)
    payload = dict(song)
    if payload.get("mixer"):
        try:
            payload["mixer"] = json.loads(payload["mixer"])
        except (TypeError, ValueError):
            payload["mixer"] = None
    return jsonify({**payload, "chords": [dict(c) for c in get_chord_grid(song_id)]})


@app.route("/api/songs/<int:song_id>", methods=["PUT"])
def api_update_song(song_id):
    song = get_song(song_id)
    if not song:
        abort(404)
    data = request.get_json(silent=True) or {}

    if "chords" in data:
        valid, invalid = validate_chord_cells(data["chords"])
        if invalid:
            return jsonify({"error": "Some chords could not be parsed.", "invalid_chords": invalid}), 400
        save_chord_grid(song_id, valid)

    metadata = {}
    for key in ("title", "tempo", "key_sig", "style", "groove",
                "scale_focus", "rms_phrasing", "melodic_temperature", "choruses", "measures", "mixer"):
        if key in data:
            metadata[key] = data[key]
    if "style" in metadata:
        metadata["style"] = normalize_style(metadata["style"])
    if "groove" in metadata or "style" in metadata:
        metadata["groove"] = normalize_groove(
            metadata.get("groove", song["groove"] if "groove" in song.keys() else "auto"),
            metadata.get("style", song["style"]),
        )
    if "key_sig" in metadata:
        metadata["key_sig"] = normalize_key(metadata["key_sig"])
    if "mixer" in metadata:
        metadata["mixer"] = normalize_mixer(metadata["mixer"]) if isinstance(metadata["mixer"], dict) else None
    if metadata:
        update_song(song_id, **metadata)
    return jsonify({"ok": True})


@app.route("/api/songs/<int:song_id>", methods=["DELETE"])
def api_delete_song(song_id):
    delete_song(song_id)
    return jsonify({"ok": True})


@app.route("/api/songs/<int:song_id>/render", methods=["POST"])
def api_render(song_id):
    song = get_song(song_id)
    if not song:
        abort(404)

    data = request.get_json(silent=True) or {}
    metadata = {}
    for key in ("title", "tempo", "key_sig", "style", "groove",
                "scale_focus", "rms_phrasing", "melodic_temperature", "choruses", "measures", "mixer"):
        if key in data:
            metadata[key] = data[key]
    if "style" in metadata:
        metadata["style"] = normalize_style(metadata["style"])
    if "groove" in metadata or "style" in metadata:
        metadata["groove"] = normalize_groove(metadata.get("groove", song["groove"] if "groove" in song.keys() else "auto"), metadata.get("style", song["style"]))
    if "key_sig" in metadata:
        metadata["key_sig"] = normalize_key(metadata["key_sig"])
    if "mixer" in metadata:
        metadata["mixer"] = normalize_mixer(metadata["mixer"]) if isinstance(metadata["mixer"], dict) else None
    if metadata:
        update_song(song_id, **metadata)
        song = get_song(song_id)

    if "chords" in data:
        valid_chords, invalid_chords = validate_chord_cells(data["chords"])
        if invalid_chords:
            return jsonify({
                "error": "Some chords could not be parsed. Fix the highlighted cells and try again.",
                "invalid_chords": invalid_chords,
            }), 400
        save_chord_grid(song_id, valid_chords)

    grid = get_chord_grid(song_id)
    if not grid:
        return jsonify({"error": "No chords to render."}), 400

    chord_list = [dict(c) for c in grid]
    tempo = clamp_tempo(song["tempo"])
    style = normalize_style(song["style"])
    groove = normalize_groove(song["groove"] if "groove" in song.keys() else "auto", style)
    render_key = uuid4().hex[:12]
    render_dir = (EXPORT_DIR / f"song-{song_id}" / render_key).resolve()
    render_dir.mkdir(parents=True, exist_ok=True)

    try:
        try:
            seed = int(data.get("seed")) if data.get("seed") is not None else None
        except (TypeError, ValueError):
            seed = None
        scale_focus = bool(data.get("scale_focus", False))
        rms_phrasing = bool(data.get("rms_phrasing", False))
        try:
            melodic_temperature = max(0, min(100, int(data.get("melodic_temperature", 35))))
        except (TypeError, ValueError):
            melodic_temperature = 35
        try:
            choruses = max(1, min(20, int(data.get("choruses", 1))))
        except (TypeError, ValueError):
            choruses = 1
        try:
            measures = max(1, min(240, int(song["measures"]))) if "measures" in song.keys() else None
        except (TypeError, ValueError):
            measures = None
        arrangement = build_arrangement(chord_list, style=style, groove=groove, seed=seed, scale_focus=scale_focus, choruses=choruses, melodic_temperature=melodic_temperature, rms_phrasing=rms_phrasing, measures=measures)
        view = str(data.get("view", "full")).lower()
        if view not in {"full", "solo", "bass", "rhythm", "drums"}:
            view = "full"
        transposition = normalize_transposition(data.get("transposition"))
        instrument = TRANSPOSING_INSTRUMENTS[transposition]
        mixer = data.get("mixer") if isinstance(data.get("mixer"), dict) else None
        export_base = export_basename(song["title"], style, groove)
        midi_target = unique_path(render_dir, export_base, ".mid")
        wav_target = unique_path(render_dir, export_base, ".wav")
        mp3_target = unique_path(render_dir, export_base, ".mp3")
        score_stem = unique_path(render_dir, export_base, ".ly").stem

        midi_path = write_midi(arrangement, tempo=tempo, output_path=midi_target, mixer=mixer)
        audio = render_audio(midi_path, wav_path=wav_target, mp3_path=mp3_target)

        # Optional per-part stems: rendered at full volume so the browser can
        # mix them live with Web Audio gain nodes instead of re-rendering.
        stem_urls = {}
        if data.get("stems"):
            for part in MIXER_TRACKS:
                stem_base = f"{export_base}-stem-{part}"
                stem_midi = write_midi(
                    arrangement, tempo=tempo,
                    output_path=unique_path(render_dir, stem_base, ".mid"),
                    mixer=stem_mixer(part),
                )
                stem_audio = render_audio(
                    stem_midi,
                    wav_path=unique_path(render_dir, stem_base, ".wav"),
                    mp3_path=unique_path(render_dir, stem_base, ".mp3"),
                )
                stem_urls[part] = export_url(stem_audio["mp3"])
        ly_source = build_lilypond_source_from_arrangement(
            arrangement,
            tempo,
            title=song["title"],
            chord_cells=arrangement.get("chord_cells", chord_list),
            key_sig=song["key_sig"],
            view=view,
            transposition=instrument["semitones"],
            transposition_label=instrument["label"],
        )
        svg_paths = render_svgs(ly_source, output_stem=score_stem, output_dir=render_dir)
        pdf_path = render_pdf(ly_source, output_stem=score_stem, output_dir=render_dir)
        render_id = save_render(song_id, render_key, midi_path=midi_path, audio_path=audio["mp3"], pdf_path=pdf_path, svg_path=svg_paths[0])
        return jsonify({
            "render_id": render_id,
            "render_key": render_key,
            "stem_urls": stem_urls or None,
            "mp3_url": export_url(audio["mp3"]),
            "midi_url": export_url(midi_path),
            "svg_url": export_url(svg_paths[0]),
            "svg_urls": [export_url(path) for path in svg_paths],
            "pdf_url": export_url(pdf_path),
            "mp3_filename": Path(audio["mp3"]).name,
            "midi_filename": Path(midi_path).name,
            "pdf_filename": Path(pdf_path).name,
            "view": view,
            "transposition": transposition,
            "phrase_metadata": arrangement.get("phrase_metadata", {}),
            "melodic_temperature": melodic_temperature,
            "rms_phrasing": rms_phrasing,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/project/export", methods=["POST"])
def api_export_project():
    data = request.get_json(silent=True) or {}
    song = {
        "title": data.get("title", "Untitled"),
        "tempo": data.get("tempo", DEFAULT_TEMPO),
        "key_sig": normalize_key(data.get("key_sig", "C")),
        "style": normalize_style(data.get("style", DEFAULT_STYLE)),
        "groove": normalize_groove(data.get("groove", "auto"), data.get("style", DEFAULT_STYLE)),
    }
    valid, invalid = validate_chord_cells(data.get("chords", []))
    if invalid:
        return jsonify({"error": "Some chords could not be parsed.", "invalid_chords": invalid}), 400
    try:
        measures = max(1, min(240, int(data.get("measures", 12))))
    except (TypeError, ValueError):
        measures = 12
    try:
        choruses = max(1, min(20, int(data.get("choruses", 1))))
    except (TypeError, ValueError):
        choruses = 1
    text = dumps_project(song, valid, measures=measures, choruses=choruses, scale_focus=bool(data.get("scale_focus", False)), melodic_temperature=data.get("melodic_temperature", 35), rms_phrasing=bool(data.get("rms_phrasing", False)))
    filename = export_basename(song["title"], song["style"], song["groove"]) + ".chordcraft.json"
    return Response(text, mimetype="application/json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.route("/api/project/export-all", methods=["POST"])
def api_export_all_formats():
    """Render the current project and return a zip with every useful format.
    Now with provider switch: ?provider=suno_v4 or provider in JSON body.
    If provider JSON is supplied, prompt.txt is generated per provider rules.
    """
    data = request.get_json(silent=True) or {}
    # provider can come from query string or body
    provider_id = request.args.get("provider") or data.get("provider") or data.get("provider_id") or "generic_biab"
    try:
        provider = load_provider(provider_id)
    except FileNotFoundError:
        # fallback to generic
        provider = load_provider("generic_biab")

    song = {
        "title": data.get("title", "Untitled"),
        "tempo": data.get("tempo", DEFAULT_TEMPO),
        "key_sig": normalize_key(data.get("key_sig", "C")),
        "style": normalize_style(data.get("style", DEFAULT_STYLE)),
        "groove": normalize_groove(data.get("groove", "auto"), data.get("style", DEFAULT_STYLE)),
    }
    # apply restraint rules from provider
    song = apply_restraints(provider, song)
    valid, invalid = validate_chord_cells(data.get("chords", []))
    if invalid:
        return jsonify({"error": "Some chords could not be parsed.", "invalid_chords": invalid}), 400
    if not valid:
        return jsonify({"error": "No chords to export."}), 400

    try:
        seed = int(data.get("seed")) if data.get("seed") is not None else None
    except (TypeError, ValueError):
        seed = None
    try:
        measures = max(1, min(240, int(data.get("measures", 12))))
    except (TypeError, ValueError):
        measures = 12
    try:
        choruses = max(1, min(20, int(data.get("choruses", 1))))
    except (TypeError, ValueError):
        choruses = 1
    try:
        melodic_temperature = max(0, min(100, int(data.get("melodic_temperature", 35))))
    except (TypeError, ValueError):
        melodic_temperature = 35
    scale_focus = bool(data.get("scale_focus", False))
    rms_phrasing = bool(data.get("rms_phrasing", False))
    mixer = data.get("mixer") if isinstance(data.get("mixer"), dict) else None
    view = str(data.get("view", "full")).lower()
    if view not in {"full", "solo", "bass", "rhythm", "drums"}:
        view = "full"
    instrument = TRANSPOSING_INSTRUMENTS[normalize_transposition(data.get("transposition"))]

    render_key = uuid4().hex[:12]
    export_base = export_basename(song["title"], song["style"], song["groove"])
    render_dir = (EXPORT_DIR / "bundles" / render_key).resolve()
    render_dir.mkdir(parents=True, exist_ok=True)

    try:
        arrangement = build_arrangement(
            valid,
            style=song["style"],
            groove=song["groove"],
            seed=seed,
            scale_focus=scale_focus,
            choruses=choruses,
            melodic_temperature=melodic_temperature,
            rms_phrasing=rms_phrasing,
            measures=measures,
        )
        midi_path = Path(write_midi(arrangement, tempo=clamp_tempo(song["tempo"]), output_path=render_dir / f"{export_base}.mid", mixer=mixer))
        audio = render_audio(midi_path, wav_path=render_dir / f"{export_base}.wav", mp3_path=render_dir / f"{export_base}.mp3")
        ly_source = build_lilypond_source_from_arrangement(
            arrangement,
            clamp_tempo(song["tempo"]),
            title=song["title"],
            chord_cells=arrangement.get("chord_cells", valid),
            key_sig=song["key_sig"],
            view=view,
            transposition=instrument["semitones"],
            transposition_label=instrument["label"],
        )
        svg_paths = [Path(p) for p in render_svgs(ly_source, output_stem=export_base, output_dir=render_dir)]
        pdf_path = Path(render_pdf(ly_source, output_stem=export_base, output_dir=render_dir))
        project_path = render_dir / f"{export_base}.chordcraft.json"
        project_path.write_text(
            dumps_project(song, valid, measures=measures, choruses=choruses, scale_focus=scale_focus, melodic_temperature=melodic_temperature, rms_phrasing=rms_phrasing),
            encoding="utf-8",
        )

        # Build provider-specific prompt.txt
        arrangement_meta = {
            "scale_focus": scale_focus,
            "rms_phrasing": rms_phrasing,
            "melodic_temperature": melodic_temperature,
            "view": view,
            "choruses": choruses,
            "measures": measures,
        }
        prompt_text = build_prompt(provider, song, valid, arrangement_meta)
        prompt_path = render_dir / f"{export_base}-{provider.get('provider_id','provider')}-prompt.txt"
        prompt_path.write_text(prompt_text, encoding="utf-8")

        # Also write a provider-specific JSON sidecar for future re-import
        sidecar_path = render_dir / f"{export_base}-{provider.get('provider_id','provider')}.json"
        sidecar_path.write_text(json.dumps({
            "provider": provider,
            "song": song,
            "arrangement_meta": arrangement_meta,
            "prompt": prompt_text
        }, indent=2), encoding="utf-8")

        zip_path = render_dir / f"{export_base}-{provider.get('provider_id','provider')}-all-formats.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Always include core files
            for path in [project_path, midi_path, Path(audio["mp3"]), pdf_path, prompt_path, sidecar_path]:
                if path.exists():
                    zf.write(path, arcname=path.name)
            for path in svg_paths:
                if path.exists():
                    zf.write(path, arcname=path.name)
            # Respect provider's export_files list for filtering if needed
            # (For now we keep all, but you can filter by extension here)

        return send_file(zip_path, mimetype="application/zip", as_attachment=True, download_name=zip_path.name)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/project/import", methods=["POST"])
def api_import_project():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        text = uploaded.read().decode("utf-8")
        project = loads_project(text)
        return jsonify(project)
    except Exception as exc:
        return jsonify({"error": f"Could not import ChordCraft project: {exc}"}), 400


@app.route("/api/project/import-midi", methods=["POST"])
def api_import_midi():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "No MIDI file uploaded."}), 400
    tmp_dir = EXPORT_DIR / "imports"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded.filename or "import.mid").suffix or ".mid"
    tmp_path = tmp_dir / f"{uuid4().hex}{suffix}"
    try:
        uploaded.save(tmp_path)
        project = import_midi_to_project(tmp_path, title=Path(uploaded.filename or "Imported MIDI").stem, style=request.form.get("style", DEFAULT_STYLE), key_sig=request.form.get("key_sig", "C"))
        return jsonify(project)
    except Exception as exc:
        return jsonify({"error": f"Could not import MIDI: {exc}"}), 400
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.route("/api/project/import-musicxml", methods=["POST"])
def api_import_musicxml():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "No MusicXML file uploaded."}), 400
    tmp_dir = EXPORT_DIR / "imports"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded.filename or "import.musicxml").suffix or ".musicxml"
    if suffix.lower() not in {".xml", ".musicxml", ".mxl"}:
        suffix = ".musicxml"
    tmp_path = tmp_dir / f"{__import__('uuid').uuid4().hex}{suffix}"
    try:
        uploaded.save(tmp_path)
        project = import_musicxml_to_project(
            tmp_path,
            title=Path(uploaded.filename or "Imported MusicXML").stem,
            style=request.form.get("style", DEFAULT_STYLE),
            key_sig=request.form.get("key_sig", "C"),
            groove=request.form.get("groove", "auto")
        )
        return jsonify(project)
    except Exception as exc:
        return jsonify({"error": f"Could not import MusicXML: {exc}"}), 400
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.route("/exports/<path:filename>")
def serve_export(filename):
    safe_path = safe_join(str(EXPORT_DIR), filename)
    if safe_path is None:
        abort(404)
    path = Path(safe_path).resolve()
    try:
        path.relative_to(EXPORT_DIR.resolve())
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_file(path)


if __name__ == "__main__":
    import os
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
