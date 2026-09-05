"""provider_export - provider switch via JSON import
Drop a new providers/*.json to add a new AI provider without code changes.
"""
import json
from pathlib import Path
from typing import List, Dict

def get_provider_dir() -> Path:
    # providers folder lives next to project root or in cwd
    # try multiple locations
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "providers",
        Path.cwd() / "providers",
        here.parent / "providers",
    ]
    for c in candidates:
        if c.exists():
            return c
    # default to first candidate
    return candidates[0]

def list_providers() -> List[Dict]:
    provider_dir = get_provider_dir()
    provider_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for f in provider_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({
                "provider_id": data.get("provider_id", f.stem),
                "display_name": data.get("display_name", f.stem),
                "file": f.name,
                "version": data.get("version", 1)
            })
        except Exception:
            continue
    return out

def load_provider(provider_id_or_path: str) -> dict:
    p = Path(provider_id_or_path)
    if p.exists() and p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    provider_dir = get_provider_dir()
    # try by id or stem
    for f in provider_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("provider_id") == provider_id_or_path or f.stem == provider_id_or_path:
                return data
        except Exception:
            continue
    raise FileNotFoundError(f"Provider {provider_id_or_path} not found in {provider_dir}")

def build_prompt(provider: dict, song: dict, chords: list, arrangement_meta: dict) -> str:
    style = song.get("style","")
    groove = song.get("groove","")
    style_map = provider.get("field_limits",{}).get("style_map",{})
    groove_map = provider.get("field_limits",{}).get("groove_map",{})
    style_text = style_map.get(style) or style_map.get("default","").format(style=style) if "{style}" in style_map.get("default","") else style_map.get(style, style)
    if not style_text:
        style_text = style
    groove_text = groove_map.get(groove) or groove_map.get("default","").format(groove=groove) if "{groove}" in groove_map.get("default","") else groove_map.get(groove, groove)
    if not groove_text:
        groove_text = groove

    temp = arrangement_meta.get("melodic_temperature", 35)
    phil_rules = provider.get("philosophy_rules",{})
    temp_rules = phil_rules.get("melodic_temperature",{})
    if temp < 35:
        phil_temp = temp_rules.get("low","")
    elif temp < 70:
        phil_temp = temp_rules.get("medium","")
    else:
        phil_temp = temp_rules.get("high","")

    phil_parts = []
    if arrangement_meta.get("scale_focus"):
        v = phil_rules.get("scale_focus")
        if v: phil_parts.append(v)
    if arrangement_meta.get("rms_phrasing"):
        v = phil_rules.get("rms_phrasing")
        if v: phil_parts.append(v)
    if phil_temp:
        phil_parts.append(phil_temp)
    philosophy = " ".join([x for x in phil_parts if x])

    chord_summary = " | ".join([f"{c['symbol']} m{c['measure']+1}" for c in chords[:16]])
    if len(chords) > 16:
        chord_summary += f" ... ({len(chords)} total)"

    template = provider.get("prompt_template","{style} {chord_summary}")
    try:
        prompt = template.format(
            style=style_text,
            groove=groove_text,
            key_sig=song.get("key_sig","C"),
            tempo=song.get("tempo",120),
            philosophy=philosophy,
            chord_summary=chord_summary,
            instrument_hint=arrangement_meta.get("view","full"),
            title=song.get("title","Untitled"),
            measures=arrangement_meta.get("measures",12),
            choruses=arrangement_meta.get("choruses",1)
        )
    except KeyError as e:
        # fallback if template has unknown key
        prompt = f"{style_text} {groove_text} {song.get('key_sig')} {song.get('tempo')}BPM {chord_summary} {philosophy}"

    max_chars = provider.get("field_limits",{}).get("prompt_max_chars", 1000)
    return prompt[:max_chars]

def apply_restraints(provider: dict, song: dict):
    rules = provider.get("restraint_rules",{})
    if not rules:
        return song
    if "max_tempo" in rules:
        song["tempo"] = min(song["tempo"], rules["max_tempo"])
    if "min_tempo" in rules:
        song["tempo"] = max(song["tempo"], rules["min_tempo"])
    return song
