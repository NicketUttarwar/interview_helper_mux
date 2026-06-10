from __future__ import annotations

from pathlib import Path


def transcribe_clip(
    wav_path: Path,
    *,
    model_name: str,
    compute_type: str,
    download_root: Path,
) -> tuple[str, float]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper not installed") from exc

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type=compute_type,
        download_root=str(download_root),
    )
    segments, _info = model.transcribe(
        str(wav_path),
        language="en",
        beam_size=1,
        temperature=0.0,
        without_timestamps=True,
        vad_filter=False,
    )
    texts: list[str] = []
    scores: list[float] = []
    for seg in segments:
        t = (seg.text or "").strip()
        if t:
            texts.append(t)
            scores.append(float(getattr(seg, "avg_logprob", -0.5)))
    if not texts:
        return "", 0.0
    text = " ".join(texts)
    conf = min(1.0, max(0.0, 1.0 + (sum(scores) / len(scores))))
    return text, conf


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False
