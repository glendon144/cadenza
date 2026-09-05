"""Filename helpers for ChordCraft rendered exports."""

from __future__ import annotations

import re
from pathlib import Path


def filename_slug(title: str | None, fallback: str = "chordcraft") -> str:
    """Return a filesystem-friendly basename derived from the song title."""
    raw = (title or fallback).strip() or fallback
    slug = re.sub(r"[^A-Za-z0-9._ -]+", "", raw).strip().replace(" ", "_")
    slug = re.sub(r"_+", "_", slug).strip("._-")
    return slug or fallback


def unique_path(directory: Path, basename: str, suffix: str) -> Path:
    """Choose basename.suffix, then basename-2.suffix, etc. if needed."""
    candidate = directory / f"{basename}{suffix}"
    if not candidate.exists():
        return candidate
    for n in range(2, 1000):
        candidate = directory / f"{basename}-{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Could not choose a unique export filename.")


def export_basename(title: str | None, style: str | None = None, groove: str | None = None) -> str:
    """Return Title-style or Title-style-clave_type for rendered files."""
    title_part = filename_slug(title)
    style_part = filename_slug(style or "style", fallback="style")
    groove_value = (groove or "auto").strip().lower()
    if groove_value and groove_value != "auto" and ("clave" in groove_value or "rumba" in groove_value or "rhumba" in groove_value):
        groove_part = filename_slug(groove_value, fallback="clave")
        return filename_slug(f"{title_part}-{style_part}-{groove_part}")
    return filename_slug(f"{title_part}-{style_part}")
