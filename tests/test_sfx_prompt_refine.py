"""API helper tests for MMAudio SFX refine routes."""

from __future__ import annotations

from interview_mux.web.server import _read_mmaudio_qa, _read_sfx_generation_meta


class _FakeCtx:
    def __init__(self, meta: dict):
        self._meta = meta
        self._files: dict[str, dict] = {}

    def artifact_exists(self, path: str) -> bool:
        if path == "run_meta.json":
            return bool(self._meta)
        return path in self._files

    def read_json(self, path: str) -> dict:
        if path == "run_meta.json":
            return self._meta
        return self._files.get(path, {})


def test_read_mmaudio_qa_empty():
    ctx = _FakeCtx({})
    assert _read_mmaudio_qa(ctx) == {"version": 1, "assets": []}


def test_read_sfx_generation_meta():
    ctx = _FakeCtx({"sfx_generation_meta": {"bed": {"cfg_strength": 3.8}}})
    meta = _read_sfx_generation_meta(ctx)
    assert meta["bed"]["cfg_strength"] == 3.8
