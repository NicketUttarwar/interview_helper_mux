from __future__ import annotations

import uuid
from pathlib import Path

from pipeline.transcription.schema import TranscriptDocument, TranscriptSegment, TranscriptWord


def transcribe_faster_whisper(
    audio_path: Path,
    *,
    interview_id: str,
    model_size: str = "base",
    language: str | None = None,
) -> TranscriptDocument:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError("Install deps: pip install -r requirements.txt") from e

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(str(audio_path), language=language, word_timestamps=True)
    revision_id = str(uuid.uuid4())
    doc = TranscriptDocument(
        interview_id=interview_id,
        revision_id=revision_id,
        provider="faster-whisper",
        model_id=model_size,
        language=info.language or language or "en",
        duration_ms=int((info.duration or 0) * 1000) if info.duration else None,
    )
    for idx, seg in enumerate(segments_iter):
        words = []
        if seg.words:
            for w in seg.words:
                words.append(
                    TranscriptWord(
                        word=w.word.strip(),
                        start_ms=int(w.start * 1000),
                        end_ms=int(w.end * 1000),
                        confidence=getattr(w, "probability", None),
                    )
                )
        doc.segments.append(
            TranscriptSegment(
                segment_index=idx,
                start_ms=int(seg.start * 1000),
                end_ms=int(seg.end * 1000),
                text=seg.text.strip(),
                words=words,
            )
        )
    return doc
