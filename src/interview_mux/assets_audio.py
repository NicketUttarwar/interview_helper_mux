from __future__ import annotations

from pathlib import Path

# Already PCM WAV — DeepFilter / ingest can read these directly.
_WAV_SUFFIXES = frozenset({".wav", ".wave"})


def is_wav_path(path: Path | str) -> bool:
    return Path(path).suffix.lower() in _WAV_SUFFIXES


def needs_wav_conversion(path: Path | str) -> bool:
    """True when the asset is not already a WAV DeepFilter/STT can open."""
    return not is_wav_path(path)


def ensure_wav_asset(source: Path) -> Path:
    """Convert any non-WAV media to a sibling ``.wav``, then return that path.

    Default pipeline contract: operators may drop mp3/mp4/m4a/flac/ogg/etc.
    under ``ASSETS/``; before DeepFilter, ingest, and hashing we always work
    from the PCM WAV sibling (created once, reused when up to date).
    """
    source = source.resolve()
    if is_wav_path(source):
        return source
    if not source.is_file():
        raise FileNotFoundError(source)

    wav_path = source.with_suffix(".wav")
    if wav_path.is_file() and wav_path.stat().st_mtime >= source.stat().st_mtime:
        return wav_path

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    # -vn: drop video if present (mp4/mov). pcm_s16le: DeepFilter-friendly WAV.
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    from interview_mux.operator_subprocess import run_command

    run_command(
        cmd,
        label=f"ffmpeg convert {source.name} → wav",
        stage="setup",
    )
    if not wav_path.is_file():
        raise RuntimeError(
            f"ffmpeg did not produce {wav_path.name} from {source.name}"
        )
    return wav_path


def repo_relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
