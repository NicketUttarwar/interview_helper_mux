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

from interview_mux.podcast_rss.cover_prompt import assemble_prompt, validate_prompt
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
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow required for cover generate mock")
        Image.new("RGB", (1400, 1400), color=(20, 40, 60)).save(dest, format="JPEG")
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
    # ECG-B3: generate asserts Apple min; publish still hard-stops too.
    assert "require_cover_min_size" in inspect.getsource(run_episode_cover_generate)
    assert "require_cover_min_size" in inspect.getsource(run_podcast_publish)


def test_ecg_b1_cover_candidates_ownership_allow() -> None:
    """ECG-B1: cascade candidate paths are owned by episode_cover_generate."""
    from interview_mux.artifact_ownership import write_permitted

    for rel in (
        "publish/cover_candidates/0.jpg",
        "publish/cover_candidates/batch_0/1.jpg",
        "publish/cover_candidates/batch_1/2.png",
    ):
        ok, reason = write_permitted(
            None, rel, "episode_cover_generate", role="producer", verb="persist"
        )
        assert ok, f"{rel} denied: {reason}"
        foreign_ok, _ = write_permitted(
            None, rel, "podcast_publish", role="producer", verb="persist"
        )
        assert not foreign_ok


def test_ecg_b2_contract_tier_llm_full() -> None:
    """ECG-B2: OpenAI Images+Vision stage is llm_full, not process."""
    from interview_mux.stage_contract import load_contract
    from interview_mux.v2.config import ALL_LLM_STAGES

    assert "episode_cover_generate" in ALL_LLM_STAGES
    doc = load_contract("episode_cover_generate")
    assert doc.tier == "llm_full"


def test_empty_cover_prompt_is_incomplete(tmp_path) -> None:
    """ECPC-B1: empty prompt must not seed-complete (honesty)."""
    from interview_mux.stage_completion import stage_artifact_incompleteness

    ctx = isolated_run_ctx(tmp_path, "ecpc_empty_prompt")
    _write_raw(
        ctx,
        "publish/cover_prompt.json",
        {
            "prompt": "",
            "rejected": True,
            "reject_reasons": ["empty_prompt"],
            "motifs": [],
            "without_clauses": [],
            "source": "test_hollow",
        },
    )
    reason = stage_artifact_incompleteness(ctx, "episode_cover_prompt_craft")
    assert reason is not None
    assert "empty" in reason


def test_nonempty_cover_prompt_completes(tmp_path) -> None:
    """ECPC-B1: non-empty harvested prompt is seed-complete."""
    from interview_mux.stage_completion import stage_artifact_incompleteness

    ctx = isolated_run_ctx(tmp_path, "ecpc_nonempty_prompt")
    prompt = assemble_prompt(["abstract geometric focal emblem"])
    assert prompt.strip()
    _write_raw(
        ctx,
        "publish/cover_prompt.json",
        {
            "prompt": prompt,
            "rejected": False,
            "reject_reasons": [],
            "motifs": ["abstract geometric focal emblem"],
            "without_clauses": [],
            "source": "harvest_after_reject",
        },
    )
    assert stage_artifact_incompleteness(ctx, "episode_cover_prompt_craft") is None
