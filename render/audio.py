"""FluidSynth → WAV → MP3 pipeline using the current or managed SoundFont."""

from __future__ import annotations

import subprocess
from urllib.request import urlopen
from pathlib import Path
from config import (
    FFMPEG_BIN, FLUIDSYNTH_BIN, MANAGED_SOUNDFONT_PATH,
    SOUNDFONT_DOWNLOAD_URL, SOUNDFONT_PATH,
)
from render.preflight import require_dependencies


def normalize_audio_mode(mode: str | None) -> str:
    return "soundfont" if str(mode or "current").lower() == "soundfont" else "current"


def managed_soundfont_available() -> bool:
    return MANAGED_SOUNDFONT_PATH.is_file() and MANAGED_SOUNDFONT_PATH.stat().st_size > 0


def download_soundfont(destination: str | Path | None = None, url: str | None = None) -> str:
    """Download the managed open-source bank after caller consent."""
    target = Path(destination or MANAGED_SOUNDFONT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".download")
    try:
        with urlopen(url or SOUNDFONT_DOWNLOAD_URL, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if temporary.stat().st_size == 0:
            raise RuntimeError("Downloaded SoundFont was empty.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target)


def soundfont_for_mode(mode: str | None) -> str:
    if normalize_audio_mode(mode) == "soundfont":
        if not managed_soundfont_available():
            raise RuntimeError("The managed SoundFont is not installed. Approve its download first.")
        return str(MANAGED_SOUNDFONT_PATH)
    return SOUNDFONT_PATH


def midi_to_wav(midi_path: str | Path, wav_path: str | Path | None = None, *, audio_mode: str = "current") -> str:
    require_dependencies(include_lilypond=False, include_audio=True)
    midi_path = Path(midi_path)
    wav_path = Path(wav_path) if wav_path else midi_path.with_suffix(".wav")
    cmd = [FLUIDSYNTH_BIN, "-ni", "-g", "1.0", "-r", "44100", "-F", str(wav_path), soundfont_for_mode(audio_mode), str(midi_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FluidSynth error:\n{result.stderr}")
    return str(wav_path)


def wav_to_mp3(wav_path: str | Path, mp3_path: str | Path | None = None) -> str:
    require_dependencies(include_lilypond=False, include_audio=True)
    wav_path = Path(wav_path)
    mp3_path = Path(mp3_path) if mp3_path else wav_path.with_suffix(".mp3")
    cmd = [FFMPEG_BIN, "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{result.stderr}")
    return str(mp3_path)


def render_audio(midi_path: str | Path, wav_path: str | Path | None = None, mp3_path: str | Path | None = None, *, audio_mode: str = "current") -> dict[str, str]:
    wav = midi_to_wav(midi_path, wav_path=wav_path, audio_mode=audio_mode)
    mp3 = wav_to_mp3(wav, mp3_path=mp3_path)
    return {"wav": wav, "mp3": mp3, "audio_mode": normalize_audio_mode(audio_mode)}
