from __future__ import annotations

import warnings
from pathlib import Path


def warn_if_likely_non_speech(input_path: Path) -> None:
    """
    Heuristic warning for sine/test tones or filenames that imply non-interview audio.
    Does not block ingest.
    """
    name = input_path.name.lower()
    hints = ("sine", "test_tone", "lavfi", "tone", "beep")
    if any(h in name for h in hints):
        warnings.warn(
            f"Input '{input_path.name}' looks like a test tone, not speech. "
            "STT and highlight reels will not produce a meaningful podcast. "
            "Use a real interview recording for production (Step 6+).",
            stacklevel=2,
        )
