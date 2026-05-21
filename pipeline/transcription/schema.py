from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TranscriptWord(BaseModel):
    word: str
    start_ms: int
    end_ms: int
    confidence: float | None = None


class TranscriptSegment(BaseModel):
    segment_index: int
    start_ms: int
    end_ms: int
    text: str
    words: list[TranscriptWord] = Field(default_factory=list)
    speaker: str | None = None


class TranscriptDocument(BaseModel):
    """Canonical transcript JSON for preset A STT."""

    interview_id: str
    revision_id: str
    provider: str
    model_id: str
    language: str = "en"
    duration_ms: int | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
