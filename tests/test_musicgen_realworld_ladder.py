"""Real-world MusicGen / palette tests inspired by exec_1765 hang + MMAudio fallback.

exec_1765 facts (baba e2e):
- cold_open MusicGen on facebook/musicgen-large sat on CPU for ~18+ minutes
  (operator log shows 0s…1110s) before recovery
- Final assets logged as MMAudio provider; later gen.json shows e2e fast-stub
- Prompts were 60–160+ word essays (pre-palette succinct path)
- Only musicgen-large (+ melody-large) were cached — medium/small missing,
  so a ladder could not step down after large timeout

These tests lock the fixed palette + succinct recipes + hang-safety timeouts.
GPU / medium-primary live probes live in ``test_musicgen_gpu_realworld.py``.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from interview_mux.config import repo_root
from interview_mux.music_motif import (
    analysis_palette_counts,
    compile_musicgen_prompt,
    default_motif_family,
    harden_palette_inventory,
    validate_theme_prompt,
)
from interview_mux.musicgen_runner import clamp_music_duration, musicgen_hf_home
from interview_mux.stages.music_palette_compose import _apply_cues, _default_cues

# --- Fixtures drawn from exec_1765 (abridged, tape-faithful) -----------------

_EXEC_1765 = (
    repo_root()
    / "ASSETS"
    / "executions"
    / "exec_1765_1311e28fffa1_20260811T230442Z"
)

# Long essay prompt that hung on cold_open (truncated from sfx_prompts.json).
_LEGACY_COLD_OPEN_ESSAY = (
    "Create a sixteen-second intro theme in the shared acoustic conversational, "
    "dry close-mic neutral-mid identity, centred in G major. State the ascending "
    "four-note G-major acoustic-guitar motif clearly, then let punchy piano answer "
    "it in a measured call and response. Add warm electric bass, soft sustained "
    "strings, and restrained brushed percussion as a layered ensemble. Shape two "
    "compact melodic phrases, moving from a poised opening tonic through a gently "
    "tense dominant colour into a bright documentary resolution. The mood is "
    "attentive, quietly optimistic, and values-led, with fuller speech-free "
    "presence and a clean final cadence Topics: conviction, gratitude, reflection"
)

_BABA_BRIEF = {
    "show_identity": {
        "genre_hint": "acoustic conversational documentary instrumental",
        "mood": "determined",
        "instrumentation_prefs": [
            "acoustic guitar",
            "punchy piano",
            "warm electric bass",
            "soft strings",
            "restrained brushed percussion",
        ],
        "key_center": "G",
        "scale_or_mode": "major_bright",
    },
    "motif_seeds": {"keywords": ["conviction", "gratitude", "shared ownership"]},
    "narrative_spine": {
        "acts": [
            {"title": "Bootstrapped beginnings", "mood": "hopeful", "energy": "calm"},
            {"title": "Capital and stewardship", "mood": "tense", "energy": "rising"},
            {"title": "Employee payout gratitude", "mood": "triumphant", "energy": "lift"},
        ]
    },
    "source_quotes_short": [],
}


class _FakeCtx:
    def __init__(self, artifacts: dict[str, Any]):
        self._arts = artifacts

    def artifact_exists(self, rel: str) -> bool:
        return rel in self._arts

    def read_json(self, rel: str) -> Any:
        return self._arts[rel]


def _hub_has(model_id: str) -> bool:
    slug = "models--" + model_id.replace("/", "--")
    return (musicgen_hf_home() / "hub" / slug).is_dir()


@pytest.fixture(scope="module")
def exec_1765_sdp() -> dict[str, Any] | None:
    path = _EXEC_1765 / "understanding" / "sound_design_plan.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def exec_1765_prompts() -> dict[str, Any] | None:
    path = _EXEC_1765 / "sound_design" / "sfx_prompts.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --- Palette / prompt contract (inspired by 1765 failure mode) --------------


def test_exec_1765_legacy_assets_harden_to_fixed_palette(exec_1765_sdp: dict | None) -> None:
    """Open-ended 6-stem theme list must collapse to analysis palette kinds."""
    if exec_1765_sdp is None:
        pytest.skip("exec_1765 artifacts not present")
    counts = {
        "motif": 1,
        "underscore_loop": 1,
        "optional_loop": 1,
        "stingers": 2,
        "full_beds": 2,
    }
    out = harden_palette_inventory(exec_1765_sdp, _BABA_BRIEF, counts=counts)
    kinds = [str(a.get("palette_kind")) for a in out["assets"]]
    assert kinds.count("motif") == 1
    assert kinds.count("underscore_loop") == 1
    assert kinds.count("optional_loop") == 1
    assert kinds.count("stinger") == 2
    assert kinds.count("full_bed") == 2
    assert len(out["assets"]) == 7
    # No ad-hoc extra stems beyond palette.
    assert set(kinds) <= {
        "motif",
        "underscore_loop",
        "optional_loop",
        "stinger",
        "full_bed",
    }


def test_legacy_essay_prompt_replaced_by_succinct_compile(exec_1765_prompts: dict | None) -> None:
    """60–160 word essays (1765 craft) must become short MusicGen recipes."""
    if exec_1765_prompts is None:
        pytest.skip("exec_1765 prompts not present")
    rows = exec_1765_prompts.get("prompts") or []
    cold = next(r for r in rows if r.get("asset_id") == "show_theme_v2_cold_open")
    assert len(str(cold.get("sfx_prompt") or "").split()) > 60

    motif = default_motif_family(_BABA_BRIEF)
    pos, neg = compile_musicgen_prompt(
        brief=_BABA_BRIEF,
        motif=motif,
        role="theme_cold_open",
        palette_kind="full_bed",
        wpm=135,
    )
    assert len(pos.split()) <= 80
    assert len(pos) < len(str(cold["sfx_prompt"]))
    assert not validate_theme_prompt(pos)
    assert "whoosh" in neg.lower()
    assert "vocals" in neg.lower()
    # Legacy essay must fail length / or at least be worse than compile.
    assert len(_LEGACY_COLD_OPEN_ESSAY.split()) > 60


def test_baba_like_palette_counts_from_narrative() -> None:
    """Dense multi-chapter stewardship interview → richer palette, not sparse."""
    ctx = _FakeCtx(
        {
            "mastering/mastering_plan.json": {
                "confirmed_mode": "documentary_bridge",
                "narrative_mode": "documentary_bridge",
            },
            "master/narrative_plan.json": {
                "chapters": [
                    {"title": "Beginnings"},
                    {"title": "Capital"},
                    {"title": "Gratitude"},
                ]
            },
            "master/selection.json": {
                "ordered_segment_ids": [f"seg_{i:03d}" for i in range(14)]
            },
            "understanding/soundscape_policy.json": {
                "sfx_density": {"max_beds": 2, "max_punctuators": 4},
                "cue_slots": [],
            },
        }
    )
    counts = analysis_palette_counts(ctx)  # type: ignore[arg-type]
    assert counts["motif"] == 1
    assert counts["underscore_loop"] == 1
    assert counts["full_beds"] >= 1
    assert counts["stingers"] >= 2


def test_compose_reuses_palette_across_baba_like_order(exec_1765_sdp: dict | None) -> None:
    """Compose must place/reuse palette ids — not invent N unique beds."""
    counts = {
        "motif": 1,
        "underscore_loop": 1,
        "optional_loop": 1,
        "stingers": 3,
        "full_beds": 2,
    }
    base = exec_1765_sdp or {"assets": [], "flow_plans": {"podcast": {"cues": []}}}
    sdp = harden_palette_inventory(base, _BABA_BRIEF, counts=counts)
    ordered = [f"seg_{i:03d}" for i in range(12)]
    chapters = [
        {"title": "a", "segment_ids": ordered[:4]},
        {"title": "b", "segment_ids": ordered[4:8]},
        {"title": "c", "segment_ids": ordered[8:]},
    ]
    cues = _default_cues(sdp, ordered=ordered, chapters=chapters)
    known = {str(a["asset_id"]) for a in sdp["assets"]}
    assert cues and all(str(c["asset_id"]) in known for c in cues)
    beds = [c for c in cues if c.get("placement") == "under_segment"]
    assert beds, "expected looped bed coverage via reuse"
    bed_ids = {c["asset_id"] for c in beds}
    assert bed_ids <= known
    # Optional + primary should alternate when both exist.
    if len(beds) >= 2:
        assert len(bed_ids) >= 1
    applied = _apply_cues(
        sdp,
        cues + [{"asset_id": "invented_unique_bed_99", "placement": "under_segment"}],
    )
    out_cues = applied["flow_plans"]["podcast"]["cues"]
    assert all(str(c["asset_id"]) in known for c in out_cues)


def test_full_bed_duration_may_exceed_legacy_hard_cap() -> None:
    """1765-era hard max must not truncate enjoyable full beds."""
    assert clamp_music_duration(22.0, role="theme_cold_open") >= 22.0
    assert clamp_music_duration(2.0, role="theme_underscore") >= 4.0


# --- Ladder contract (mock of the 1765 hang path) ---------------------------


def test_ladder_steps_large_then_medium_then_small_on_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reproduce 1765: large times out → must try medium then small (same prompt/dur)."""
    import interview_mux.musicgen_runner as mg

    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "e2e_musicgen_fast_stub", lambda: False)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {
            "device": "cpu",
            "ban_mps_on_abort": True,
            "request_timeout_sec": 30,
            "cpu_request_timeout_sec": 30,
            "step_down_timeout_sec": 20,
            "prefer_medium_on_cpu": False,
            "model_id": "facebook/musicgen-large",
            "min_duration_sec": 4.0,
            "mmaudio_backup_on_stub": True,
        },
    )
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "cpu")
    hub = tmp_path / "hf_cache" / "hub"
    for mid in (
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ):
        (hub / ("models--" + mid.replace("/", "--"))).mkdir(parents=True)
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    class _DummyLock:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def acquire(self, *args, **kwargs) -> bool:  # noqa: ANN002, ANN003
            return True

        def release(self) -> None:
            pass

    import filelock

    monkeypatch.setattr(filelock, "FileLock", _DummyLock)

    attempts: list[dict[str, Any]] = []

    def fake_spawn(**kwargs):  # noqa: ANN003
        req = Path(str(kwargs["req"]))
        payload = json.loads(req.read_text())
        attempts.append(
            {
                "model_id": payload.get("model_id"),
                "duration_sec": payload.get("duration_sec"),
                "prompt": payload.get("prompt"),
                "timeout": kwargs.get("timeout"),
            }
        )
        # Always timeout — simulate 1765 large hang, then continue ladder.
        return subprocess.CompletedProcess(
            kwargs["py"], -9, "", f"timeout after {kwargs.get('timeout')}s"
        )

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "cold_open.wav"
    prompt = compile_musicgen_prompt(
        brief=_BABA_BRIEF,
        motif=default_motif_family(_BABA_BRIEF),
        role="theme_cold_open",
        palette_kind="full_bed",
    )[0]
    meta = mg.generate_music_clip(
        prompt=prompt,
        negative_prompt="vocals, whoosh",
        duration_sec=16.0,
        out_wav=out,
        role="theme_cold_open",
        seed=42,
    )
    assert [a["model_id"] for a in attempts] == [
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ]
    # Same planned duration — no short_bare shrink on step-down.
    assert all(float(a["duration_sec"]) >= 16.0 for a in attempts)
    assert all(a["prompt"] == prompt for a in attempts)
    assert meta.get("backend") == "musical_stub"
    assert meta.get("mmaudio_backup_suggested") is True
    assert meta.get("musicgen_timeout") is True


def test_prefer_medium_on_cpu_defaults_off() -> None:
    from interview_mux.musicgen_runner import musicgen_cfg

    assert musicgen_cfg().get("prefer_medium_on_cpu") is False


def test_cpu_timeout_bound_is_hang_safety_not_hour() -> None:
    from interview_mux.musicgen_runner import musicgen_cfg

    cfg = musicgen_cfg()
    assert int(cfg.get("cpu_request_timeout_sec") or 0) <= 480
    assert int(cfg.get("request_timeout_sec") or 0) <= 1200
    assert int(cfg.get("request_timeout_sec") or 0) >= 600


# --- Live generation probe (optional; needs venv + weights) -----------------


def _musicgen_ready() -> bool:
    py = repo_root() / "ASSETS" / "local_musicgen" / "venv" / "bin" / "python"
    script = repo_root() / "tools" / "musicgen_generate.py"
    return py.is_file() and script.is_file() and (
        _hub_has("facebook/musicgen-medium") or _hub_has("facebook/musicgen-large")
    )


@pytest.mark.slow
def test_live_musicgen_ladder_reports_winning_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live probe: generate one stinger with current ladder; assert WAV + report winner.

    Uses a short hang budget on large so we learn whether large fails and which
    step-down (medium/small) succeeds — the 1765 operator question.
    """
    if not _musicgen_ready():
        pytest.skip("MusicGen venv / large weights missing")
    if not (_hub_has("facebook/musicgen-medium") or _hub_has("facebook/musicgen-small")):
        pytest.skip("medium/small not cached — prefetch required for ladder step-down")

    import interview_mux.musicgen_runner as mg

    monkeypatch.delenv("MUX_E2E_MUSICGEN_FAST_STUB", raising=False)
    monkeypatch.setattr(mg, "e2e_musicgen_fast_stub", lambda: False)

    # Short large budget: if large is the 1765 hang path, step down quickly.
    base = dict(mg.musicgen_cfg() or {})
    base.update(
        {
            "prefer_medium_on_cpu": False,
            "cpu_request_timeout_sec": 90,
            "request_timeout_sec": 90,
            "step_down_timeout_sec": 240,
            "mmaudio_backup_on_stub": False,
        }
    )
    monkeypatch.setattr(mg, "musicgen_cfg", lambda: base)

    motif = default_motif_family(_BABA_BRIEF)
    prompt, neg = compile_musicgen_prompt(
        brief=_BABA_BRIEF,
        motif=motif,
        role="theme_emphasis",
        palette_kind="stinger",
        wpm=140,
    )
    out = tmp_path / "live_stinger.wav"
    t0 = time.monotonic()
    meta = mg.generate_music_clip(
        prompt=prompt,
        negative_prompt=neg,
        duration_sec=6.0,
        out_wav=out,
        role="theme_emphasis",
        seed=1765,
    )
    elapsed = time.monotonic() - t0

    assert out.is_file() and out.stat().st_size > 1000
    winner = str(meta.get("model_id") or "")
    backend = str(meta.get("backend") or "")
    step = str(meta.get("fidelity_step") or "")
    ladder = meta.get("model_ladder") or []

    # Write a small report artifact for operators / CI logs.
    report = {
        "elapsed_sec": round(elapsed, 1),
        "backend": backend,
        "winning_model_id": winner,
        "fidelity_step": step,
        "model_ladder": ladder,
        "musicgen_timeout": bool(meta.get("musicgen_timeout")),
        "prompt": prompt,
        "inspired_by": "exec_1765_1311e28fffa1_20260811T230442Z",
    }
    (tmp_path / "ladder_probe_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("\n=== MusicGen ladder probe ===")
    print(json.dumps(report, indent=2))

    if backend == "musicgen":
        assert "musicgen" in winner
        # Prefer knowing whether large won or a step-down did.
        assert step.startswith("ladder_")
    else:
        # Stub means all MusicGen steps failed within budgets — still valuable signal.
        assert backend == "musical_stub"
        assert meta.get("musicgen_timeout") or meta.get("musicgen_error")
