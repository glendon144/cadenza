from __future__ import annotations

import json

from database.db import db_cursor


def init_db() -> None:
    with db_cursor() as cur:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS songs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL DEFAULT 'Untitled',
                tempo       INTEGER NOT NULL DEFAULT 120,
                key_sig     TEXT    NOT NULL DEFAULT 'C',
                style       TEXT    NOT NULL DEFAULT 'jazz',
                groove      TEXT    NOT NULL DEFAULT 'auto',
                scale_focus INTEGER NOT NULL DEFAULT 0,
                rms_phrasing INTEGER NOT NULL DEFAULT 0,
                melodic_temperature INTEGER NOT NULL DEFAULT 35,
                choruses    INTEGER NOT NULL DEFAULT 1,
                measures    INTEGER NOT NULL DEFAULT 12,
                mixer       TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chord_cells (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id     INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                measure     INTEGER NOT NULL,
                beat        INTEGER NOT NULL,
                symbol      TEXT    NOT NULL,
                duration    REAL    NOT NULL DEFAULT 1.0,
                UNIQUE(song_id, measure, beat)
            );

            CREATE TABLE IF NOT EXISTS renders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id     INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                render_key  TEXT    NOT NULL,
                midi_path   TEXT,
                audio_path  TEXT,
                pdf_path    TEXT,
                svg_path    TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Light migration for databases created by the original prototype.
        cur.execute("PRAGMA table_info(songs)")
        song_cols = {row[1] for row in cur.fetchall()}
        if "groove" not in song_cols:
            cur.execute("ALTER TABLE songs ADD COLUMN groove TEXT DEFAULT 'auto'")
        for col, ddl in (
            ("scale_focus", "ALTER TABLE songs ADD COLUMN scale_focus INTEGER NOT NULL DEFAULT 0"),
            ("rms_phrasing", "ALTER TABLE songs ADD COLUMN rms_phrasing INTEGER NOT NULL DEFAULT 0"),
            ("melodic_temperature", "ALTER TABLE songs ADD COLUMN melodic_temperature INTEGER NOT NULL DEFAULT 35"),
            ("choruses", "ALTER TABLE songs ADD COLUMN choruses INTEGER NOT NULL DEFAULT 1"),
            ("measures", "ALTER TABLE songs ADD COLUMN measures INTEGER NOT NULL DEFAULT 12"),
            ("mixer", "ALTER TABLE songs ADD COLUMN mixer TEXT"),
        ):
            if col not in song_cols:
                cur.execute(ddl)

        cur.execute("PRAGMA table_info(renders)")
        cols = {row[1] for row in cur.fetchall()}
        if "render_key" not in cols:
            cur.execute("ALTER TABLE renders ADD COLUMN render_key TEXT DEFAULT ''")
        if "svg_path" not in cols:
            cur.execute("ALTER TABLE renders ADD COLUMN svg_path TEXT")


def clamp_tempo(value, default=120) -> int:
    try:
        tempo = int(value)
    except (TypeError, ValueError):
        return default
    return max(30, min(360, tempo))


def _clamp_int(value, default: int, low: int, high: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def create_song(title="Untitled", tempo=120, key_sig="C", style="jazz", groove="auto") -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO songs (title, tempo, key_sig, style, groove) VALUES (?,?,?,?,?)",
            (str(title or "Untitled")[:120], clamp_tempo(tempo), str(key_sig or "C")[:12], str(style or "jazz")[:24], str(groove or "auto")[:24]),
        )
        return int(cur.lastrowid)


def get_song(song_id: int):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM songs WHERE id=?", (song_id,))
        return cur.fetchone()


def list_songs():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM songs ORDER BY updated_at DESC, id DESC")
        return cur.fetchall()


def update_song(song_id: int, **kwargs) -> None:
    allowed = {"title", "tempo", "key_sig", "style", "groove",
               "scale_focus", "rms_phrasing", "melodic_temperature", "choruses", "measures", "mixer"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if "tempo" in fields:
        fields["tempo"] = clamp_tempo(fields["tempo"])
    if "title" in fields:
        fields["title"] = str(fields["title"] or "Untitled")[:120]
    if "key_sig" in fields:
        fields["key_sig"] = str(fields["key_sig"] or "C")[:12]
    if "style" in fields:
        fields["style"] = str(fields["style"] or "jazz")[:24]
    if "groove" in fields:
        fields["groove"] = str(fields["groove"] or "auto")[:24]
    if "scale_focus" in fields:
        fields["scale_focus"] = 1 if fields["scale_focus"] else 0
    if "rms_phrasing" in fields:
        fields["rms_phrasing"] = 1 if fields["rms_phrasing"] else 0
    if "melodic_temperature" in fields:
        fields["melodic_temperature"] = _clamp_int(fields["melodic_temperature"], 35, 0, 100)
    if "choruses" in fields:
        fields["choruses"] = _clamp_int(fields["choruses"], 1, 1, 20)
    if "measures" in fields:
        fields["measures"] = _clamp_int(fields["measures"], 12, 1, 240)
    if "mixer" in fields:
        fields["mixer"] = json.dumps(fields["mixer"]) if isinstance(fields["mixer"], dict) else None
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with db_cursor() as cur:
        cur.execute(
            f"UPDATE songs SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (*fields.values(), song_id),
        )


def delete_song(song_id: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM songs WHERE id=?", (song_id,))


def save_chord_grid(song_id: int, cells: list[dict]) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM chord_cells WHERE song_id=?", (song_id,))
        cur.executemany(
            "INSERT INTO chord_cells (song_id, measure, beat, symbol, duration) VALUES (?,?,?,?,?)",
            [
                (
                    song_id,
                    int(c.get("measure", 0)),
                    int(c.get("beat", 0)),
                    str(c.get("symbol", "")).strip()[:40],
                    float(c.get("duration", 1.0)),
                )
                for c in cells
            ],
        )
        cur.execute("UPDATE songs SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (song_id,))


def get_chord_grid(song_id: int):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM chord_cells WHERE song_id=? ORDER BY measure, beat", (song_id,))
        return cur.fetchall()


def save_render(song_id: int, render_key: str, midi_path=None, audio_path=None, pdf_path=None, svg_path=None) -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO renders (song_id, render_key, midi_path, audio_path, pdf_path, svg_path) VALUES (?,?,?,?,?,?)",
            (song_id, render_key, str(midi_path) if midi_path else None, str(audio_path) if audio_path else None,
             str(pdf_path) if pdf_path else None, str(svg_path) if svg_path else None),
        )
        return int(cur.lastrowid)
