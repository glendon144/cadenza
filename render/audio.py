"""FluidSynth → WAV → MP3 pipeline using subprocess."""

from __future__ import annotations

import subprocess
from pathlib import Path
from config import FFMPEG_BIN, FLUIDSYNTH_BIN, SOUNDFONT_PATH
from render.preflight import require_dependencies


def midi_to_wav(midi_path: str | Path, wav_path: str | Path | None = None) -> str:
    require_dependencies(include_lilypond=False, include_audio=True)
    midi_path = Path(midi_path)
    wav_path = Path(wav_path) if wav_path else midi_path.with_suffix(".wav")
    cmd = [FLUIDSYNTH_BIN, "-ni", "-g", "1.0", "-r", "44100", "-F", str(wav_path), SOUNDFONT_PATH, str(midi_path)]
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


def render_audio(midi_path: str | Path, wav_path: str | Path | None = None, mp3_path: str | Path | None = None) -> dict[str, str]:
    wav = midi_to_wav(midi_path, wav_path=wav_path)
    mp3 = wav_to_mp3(wav, mp3_path=mp3_path)
    return {"wav": wav, "mp3": mp3}
