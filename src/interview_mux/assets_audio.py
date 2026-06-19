from __future__ import annotations

from pathlib import Path

M4A_SUFFIX = ".m4a"


def ensure_wav_asset(source: Path) -> Path:
    """Convert `.m4a` to sibling `.wav` in the same directory; return the WAV path."""
    source = source.resolve()
    if source.suffix.lower() != M4A_SUFFIX:
        return source
    if not source.is_file():
        raise FileNotFoundError(source)

    wav_path = source.with_suffix(".wav")
    if wav_path.is_file() and wav_path.stat().st_mtime >= source.stat().st_mtime:
        return wav_path

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    from interview_mux.operator_subprocess import run_command

    run_command(cmd, label=f"ffmpeg convert {source.name} → wav", stage="setup")
    return wav_path


def repo_relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
