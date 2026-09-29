"""WAV hash memo stays correct when the file changes (ISSUES 60)."""

from __future__ import annotations

import os
import time

from interview_mux import vo_synthesis_audit as v


def test_hash_is_memoized_and_invalidated_by_a_rewrite(tmp_path) -> None:
    v._SHA_CACHE.clear()
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF-one")
    first = v.wav_content_sha256(p)
    assert v.wav_content_sha256(p) == first
    assert len(v._SHA_CACHE) == 1
    p.write_bytes(b"RIFF-two-longer")
    later = time.time() + 5
    os.utime(p, (later, later))
    second = v.wav_content_sha256(p)
    assert second != first
