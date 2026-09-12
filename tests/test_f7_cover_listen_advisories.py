"""F7 cover / listen advisories: warn unless catastrophic; harvest then generate.

Fixture intent from exec_5404 / exec_5570 cover-prompt noise and listen quirks.
Does not resume those runs. 1C: ship listen misses are advisory above
catastrophic floors. 2B: invalid craft harvests a backup prompt and still
tries generate. 3C: Apple min-size at package remains a hard stop.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from interview_mux.podcast_rss.cover_prompt import validate_prompt
from interview_mux.podcast_rss.openai_cover import require_cover_min_size
from interview_mux.stages.podcast_publish import (
    _persist_cover_artifacts,
    run_episode_cover_generate,
    run_podcast_publish,
)
from run_fixtures import isolated_run_ctx

_FIX = Path(__file__).resolve().parent / "fixtures" / "f7_cover_listen_advisories"
_META = json.loads((_FIX / "meta.json").read_text(encoding="utf-8"))


def _write_raw(ctx, rel: str, data: dict) -> None:
    path = ctx.path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_invalid_llm_prompt_harvests_valid_backup(tmp_path) -> None:
    json.loads((_FIX / "meta.json").read_text(encoding="utf-8"))
    ctx = isolated_run_ctx(tmp_path, "f7_harvest_prompt")
    _persist_cover_artifacts(
        ctx,
        {"prompt": str(_META["invalid_llm_prompt"]), "motifs": ["mic"]},
        source="llm_volley",
    )
    doc = ctx.read_json("publish/cover_prompt.json")
    assert doc["rejected"] is False
    assert doc["source"] == "harvest_after_reject"
    assert validate_prompt(str(doc.get("prompt") or "")) == []


def test_rejected_prompt_still_tries_generate(tmp_path, monkeypatch) -> None:
    ctx = isolated_run_ctx(tmp_path, "f7_generate_retry")
    _write_raw(
        ctx,
        "publish/cover_prompt.json",
        {
            "prompt": str(_META["invalid_llm_prompt"]),
            "rejected": True,
            "reject_reasons": ["realism_language"],
            "motifs": [],
            "without_clauses": [],
        },
    )
    generated: list[str] = []

    def fake_candidates(*, prompt: str, dest_dir: Path, settings: dict):
        generated.append(prompt)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / "0.jpg"
        out.write_bytes(b"fake-jpg")
        return [out]

    monkeypatch.setattr(
        "interview_mux.stages.podcast_publish._vision_pick_cfg",
        lambda ctx=None: {
            "enabled": False,
            "max_rebatch": 0,
            "on_final_fail": "show_fallback",
            "primary_criterion": "brilliance",
        },
    )
    monkeypatch.setattr(
        "interview_mux.podcast_rss.openai_cover.generate_cover_candidates",
        fake_candidates,
    )

    def fake_square(path, **kwargs):
        dest = kwargs.get("dest") or path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"cover")
        return dest

    monkeypatch.setattr(
        "interview_mux.podcast_rss.openai_cover.ensure_square_cover",
        fake_square,
    )
    show_calls: list[str] = []
    monkeypatch.setattr(
        "interview_mux.stages.podcast_publish._copy_show_fallback",
        lambda _ctx, dest, *, reason: show_calls.append(reason) or dest,
    )
    run_episode_cover_generate(ctx)
    assert generated, "expected harvest backup to still call OpenAI generate"
    assert not show_calls
    disk = ctx.read_json("publish/cover_prompt.json")
    assert disk["rejected"] is False
    assert disk["source"] == "harvest_generate_retry"


def test_apple_min_size_still_hard_stops(tmp_path) -> None:
    tiny = tmp_path / "tiny.jpg"
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow required for cover min-size check")
    Image.new("RGB", (64, 64), color=(10, 10, 10)).save(tiny, format="JPEG")
    with pytest.raises(RuntimeError, match="at least 1400"):
        require_cover_min_size(tiny, min_px=int(_META["apple_min_cover_px"]))
    src = inspect.getsource(run_podcast_publish)
    assert "require_cover_min_size" in src
