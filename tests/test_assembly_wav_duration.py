"""Tests for EDL VO duration probing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from interview_mux.stages import assembly


def test_wav_duration_ms_raises_on_empty_ffprobe(monkeypatch):
    proc = MagicMock()
    proc.stdout = ""
    monkeypatch.setattr(assembly, "run_command", lambda *a, **k: proc)
    with pytest.raises(RuntimeError, match="unreadable VO duration"):
        assembly._wav_duration_ms(Path("/tmp/missing.wav"))
