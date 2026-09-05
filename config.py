"""Configuration for ChordCraft.

Values may be overridden with environment variables.  The defaults are tuned
for local development on macOS or Linux.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = Path(os.environ.get("CHORDCRAFT_EXPORT_DIR", BASE_DIR / "exports")).resolve()
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = Path(os.environ.get("CHORDCRAFT_DATABASE", BASE_DIR / "chordcraft.db")).resolve()

DEFAULT_SOUNDFONT_PATHS = [
    "/opt/soundfonts/GeneralUser-GS/GeneralUser-GS.sf2",
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/GeneralUser_GS.sf2",
    "/usr/local/share/fluidsynth/GeneralUser GS.sf2",
    "/opt/homebrew/share/sounds/sf2/FluidR3_GM.sf2",
]

_configured_soundfont = os.environ.get("SOUNDFONT_PATH")
SOUNDFONT_PATH = (
    _configured_soundfont
    if _configured_soundfont and Path(_configured_soundfont).exists()
    else next((path for path in DEFAULT_SOUNDFONT_PATHS if Path(path).exists()), DEFAULT_SOUNDFONT_PATHS[0])
)

FLUIDSYNTH_BIN = os.environ.get("FLUIDSYNTH_BIN", "fluidsynth")
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
LILYPOND_BIN = os.environ.get("LILYPOND_BIN", "lilypond")

DEFAULT_TEMPO = 120
DEFAULT_KEY = "C"
DEFAULT_STYLE = "jazz"
MAX_MEASURES = 128
