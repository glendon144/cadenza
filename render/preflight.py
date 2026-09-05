"""Dependency checks for ChordCraft's external render tools."""

from __future__ import annotations

import shutil
from pathlib import Path
from config import FFMPEG_BIN, FLUIDSYNTH_BIN, LILYPOND_BIN, SOUNDFONT_PATH


def check_dependencies(include_lilypond: bool = True, include_audio: bool = True) -> dict:
    checks = {}
    if include_audio:
        checks["fluidsynth"] = bool(shutil.which(FLUIDSYNTH_BIN))
        checks["ffmpeg"] = bool(shutil.which(FFMPEG_BIN))
        checks["soundfont"] = Path(SOUNDFONT_PATH).exists()
    if include_lilypond:
        checks["lilypond"] = bool(shutil.which(LILYPOND_BIN))
    missing = [name for name, ok in checks.items() if not ok]
    return {"ok": not missing, "checks": checks, "missing": missing}


def require_dependencies(include_lilypond: bool = True, include_audio: bool = True) -> None:
    result = check_dependencies(include_lilypond=include_lilypond, include_audio=include_audio)
    if not result["ok"]:
        readable = ", ".join(result["missing"])
        raise RuntimeError(f"Missing render dependencies: {readable}. Install them or set the matching *_BIN/SOUNDFONT_PATH environment variables.")
