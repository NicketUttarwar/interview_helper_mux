from __future__ import annotations

from pathlib import Path

import pytest

from interview_mux.source_audio_hash import (
    compute_source_audio_hash,
    hashes_match,
    normalized_source_audio_hash,
    parse_hash_from_run_id,
)


def test_parse_hash_from_run_id_new_format() -> None:
    rid = "exec_003_a3f2b1c9d4e5_20250609T143022Z"
    assert parse_hash_from_run_id(rid) == "a3f2b1c9d4e5"


def test_parse_hash_from_run_id_legacy() -> None:
    assert parse_hash_from_run_id("exec_003_20250609T143022Z") is None


def test_hashes_match_full_and_short() -> None:
    full = "a" * 64
    assert hashes_match(full, full)
    assert hashes_match(full, "a" * 12)


def test_compute_hash_stable_for_wav(tmp_path: Path) -> None:
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 100)
    h1 = compute_source_audio_hash(wav)
    h2 = normalized_source_audio_hash(wav)
    assert len(h1) == 64
    assert len(h2) == 12
    assert h1.startswith(h2)
