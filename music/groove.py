"""Groove and clave helpers for ChordCraft accompaniment."""

from __future__ import annotations

SUPPORTED_GROOVES = {"auto", "clave_2_3", "clave_3_2", "rumba_2_3", "rumba_3_2", "rhumba_2_3", "rhumba_3_2"}
LATIN_STYLES = {"bossa", "samba"}


def normalize_style(style: str | None) -> str:
    value = (style or "jazz").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "bossa_nova": "bossa",
        "latin": "bossa",
        "straight_ahead": "jazz",
        "swing": "jazz",
    }
    return aliases.get(value, value if value in {"jazz", "bossa", "samba", "pop"} else "jazz")


def normalize_groove(groove: str | None, style: str | None = None) -> str:
    style = normalize_style(style)
    value = (groove or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "23": "clave_2_3",
        "2_3": "clave_2_3",
        "2-3": "clave_2_3",
        "son_2_3": "clave_2_3",
        "son_23": "clave_2_3",
        "clave23": "clave_2_3",
        "32": "clave_3_2",
        "3_2": "clave_3_2",
        "3-2": "clave_3_2",
        "son_3_2": "clave_3_2",
        "son_32": "clave_3_2",
        "clave32": "clave_3_2",
        "rumba23": "rumba_2_3",
        "rumba_23": "rumba_2_3",
        "rumba_2_3": "rumba_2_3",
        "rumba_2-3": "rumba_2_3",
        "rhumba23": "rumba_2_3",
        "rhumba_23": "rumba_2_3",
        "rhumba_2_3": "rumba_2_3",
        "rhumba_2-3": "rumba_2_3",
        "rumba32": "rumba_3_2",
        "rumba_32": "rumba_3_2",
        "rumba_3_2": "rumba_3_2",
        "rumba_3-2": "rumba_3_2",
        "rhumba32": "rumba_3_2",
        "rhumba_32": "rumba_3_2",
        "rhumba_3_2": "rumba_3_2",
        "rhumba_3-2": "rumba_3_2",
        "default": "auto",
    }
    value = aliases.get(value, value)
    if value not in SUPPORTED_GROOVES:
        value = "auto"
    if value == "auto":
        if style == "samba":
            return "clave_2_3"
        if style == "bossa":
            return "clave_3_2"
    return value


def clave_offsets_for_measure(measure_index: int, groove: str, style: str | None = None) -> list[float]:
    """Return clave-like chord-comping offsets inside one 4/4 measure.

    The pattern spans two measures.  A 3-side measure has three attacks;
    a 2-side measure has two attacks.  These are not intended as a scholarly
    percussion transcription; they are a practical comping grid that gives the
    generated accompaniment a recognizable Latin push.
    """
    groove = normalize_groove(groove, style)
    three_side_first = groove in {"clave_3_2", "rumba_3_2", "rhumba_3_2"}
    rumba_family = groove in {"rumba_2_3", "rumba_3_2", "rhumba_2_3", "rhumba_3_2"}

    is_three_side = (measure_index % 2 == 0) == three_side_first
    if is_three_side:
        # Son clave:    1, & of 2, 4    -> [0.0, 1.5, 3.0]
        # Rhumba clave: 1, & of 2, & of 4 -> delay the third attack by half a beat.
        return [0.0, 1.5, 3.5] if rumba_family else [0.0, 1.5, 3.0]
    return [1.0, 2.5]
