"""Novel GPU-first MusicGen / palette tests inspired by exec_1765 failure.

exec_1765 (Full-auto) facts:
- Primary was facebook/musicgen-large on **CPU**
- cold_open sat ~18+ minutes then recovered via MMAudio / e2e stub
- Prompts were long essays; medium/small often uncached

Current ship contract (M1 16GB):
- musicgen.device=auto → **MPS**
- musicgen.model_id=facebook/musicgen-large (ladder large→medium→small)
- succinct compile_musicgen_prompt recipes
- machine-wide local_gpu serialize + cooldown
- primary hang budget ``request_timeout_sec`` sized for real MPS large (~900s)

Live ``@pytest.mark.slow`` tests require MusicGen venv + HF weights and exercise
real GPU generation for the first time under these defaults.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from interview_mux.config import merged_config, repo_root
from interview_mux.music_motif import (
    compile_musicgen_prompt,
    default_motif_family,
    validate_theme_prompt,
)
from interview_mux.musicgen_runner import (
    effective_musicgen_device,
    musicgen_cfg,
    musicgen_hf_home,
)

_EXEC_1765 = (
    repo_root()
    / "ASSETS"
    / "executions"
    / "exec_1765_1311e28fffa1_20260811T230442Z"
)

_FULL_AUTO_BRIEF = {
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
}


def _hub_has(model_id: str) -> bool:
    slug = "models--" + model_id.replace("/", "--")
    return (musicgen_hf_home() / "hub" / slug).is_dir()


def _musicgen_ready(*, need: str = "facebook/musicgen-large") -> bool:
    py = repo_root() / "ASSETS" / "local_musicgen" / "venv" / "bin" / "python"
    script = repo_root() / "tools" / "musicgen_generate.py"
    return py.is_file() and script.is_file() and _hub_has(need)


def _succinct_prompts(*, role: str, palette_kind: str) -> tuple[str, str]:
    return compile_musicgen_prompt(
        brief=_FULL_AUTO_BRIEF,
        motif=default_motif_family(_FULL_AUTO_BRIEF),
        role=role,
        palette_kind=palette_kind,
        wpm=140,
    )


# --- Shipped defaults / contract --------------------------------------------


def test_shipped_defaults_gpu_large_first_ladder() -> None:
    """Regression lock: large-first on GPU (not the 1765 CPU+tight-timeout combo)."""
    cfg = musicgen_cfg()
    assert str(cfg.get("device") or "") == "auto"
    assert "musicgen-large" in str(cfg.get("model_id") or "")
    assert int(cfg.get("request_timeout_sec") or 0) >= 600
    assert effective_musicgen_device() == "mps"
    gpu = (merged_config().get("local_gpu") or {})
    assert gpu.get("serialize") is True
    assert float(gpu.get("cooldown_sec") or 0) == 5.0


def test_exec_1765_cold_open_request_was_cpu_large() -> None:
    """Ground truth from the failed run — documents what we are fixing."""
    req = _EXEC_1765 / "sound_design" / "assets" / "show_theme_v2_cold_open.request.json"
    gen = _EXEC_1765 / "sound_design" / "assets" / "show_theme_v2_cold_open.gen.json"
    if not req.is_file() or not gen.is_file():
        pytest.skip("exec_1765 cold_open artifacts missing")
    request = json.loads(req.read_text(encoding="utf-8"))
    meta = json.loads(gen.read_text(encoding="utf-8"))
    assert request.get("device") == "cpu"
    assert "musicgen-large" in str(request.get("model_id") or "")
    # Final artifact on that run was stub/MMAudio recovery, not a clean MusicGen win.
    assert meta.get("backend") in {"musical_stub", "mmaudio", "musicgen"}
    assert meta.get("device") in {None, "cpu"} or "cpu" in str(meta.get("device") or "cpu")


def test_current_compile_is_shorter_than_1765_essay_prompt() -> None:
    prompts_path = _EXEC_1765 / "sound_design" / "sfx_prompts.json"
    if not prompts_path.is_file():
        pytest.skip("exec_1765 sfx_prompts missing")
    rows = json.loads(prompts_path.read_text(encoding="utf-8")).get("prompts") or []
    cold = next(r for r in rows if r.get("asset_id") == "show_theme_v2_cold_open")
    legacy = str(cold.get("sfx_prompt") or "")
    pos, neg = _succinct_prompts(role="theme_cold_open", palette_kind="full_bed")
    assert len(legacy.split()) > 60
    assert len(pos.split()) <= 80
    assert len(pos) < len(legacy)
    assert not validate_theme_prompt(pos)
    assert "vocals" in neg.lower()


def test_default_ladder_large_then_medium_then_small_on_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Shipped primary large must step to medium then small."""
    import interview_mux.musicgen_runner as mg

    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {
            "device": "auto",
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
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "mps")
    hub = tmp_path / "hf_cache" / "hub"
    for mid in (
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ):
        (hub / ("models--" + mid.replace("/", "--"))).mkdir(parents=True)
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    attempts: list[str] = []

    def fake_spawn(**kwargs):  # noqa: ANN003
        payload = json.loads(Path(str(kwargs["req"])).read_text())
        attempts.append(str(payload.get("model_id")))
        return subprocess.CompletedProcess(
            kwargs["py"], -9, "", f"timeout after {kwargs.get('timeout')}s"
        )

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "stinger.wav"
    prompt, neg = _succinct_prompts(role="theme_emphasis", palette_kind="stinger")
    meta = mg.generate_music_clip(
        prompt=prompt,
        negative_prompt=neg,
        duration_sec=6.0,
        out_wav=out,
        role="theme_emphasis",
        seed=1765,
    )
    assert attempts == [
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ]
    assert meta.get("backend") == "musical_stub"
    assert meta.get("mmaudio_backup_suggested") is True


def test_payload_device_is_mps_when_effective_mps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Request JSON must ask for MPS (first GPU path), not the 1765 cpu hardcode."""
    import interview_mux.musicgen_runner as mg

    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {
            "device": "auto",
            "ban_mps_on_abort": True,
            "request_timeout_sec": 60,
            "step_down_timeout_sec": 30,
            "model_id": "facebook/musicgen-large",
            "min_duration_sec": 4.0,
            "mmaudio_backup_on_stub": False,
        },
    )
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "mps")
    hub = tmp_path / "hf_cache" / "hub"
    (hub / "models--facebook--musicgen-large").mkdir(parents=True)
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    seen: dict[str, Any] = {}

    def fake_spawn(**kwargs):  # noqa: ANN003
        payload = json.loads(Path(str(kwargs["req"])).read_text())
        seen.update(payload)
        out = Path(str(payload["out_wav"]))
        out.write_bytes(b"RIFF" + b"\x00" * 2000)
        return subprocess.CompletedProcess(kwargs["py"], 0, "ok", "")

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "ok.wav"
    prompt, neg = _succinct_prompts(role="theme_emphasis", palette_kind="stinger")
    meta = mg.generate_music_clip(
        prompt=prompt,
        negative_prompt=neg,
        duration_sec=6.0,
        out_wav=out,
        role="theme_emphasis",
        seed=1,
    )
    assert seen.get("device") == "mps"
    assert seen.get("model_id") == "facebook/musicgen-large"
    assert meta.get("backend") == "musicgen"
    assert meta.get("device") == "mps"


def test_ladder_stepdowns_stay_on_mps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After primary timeout, medium/small must still request MPS (not CPU thrash)."""
    import interview_mux.musicgen_runner as mg

    monkeypatch.setattr(mg, "musicgen_enabled", lambda: True)
    monkeypatch.setattr(mg, "musicgen_venv_python", lambda: tmp_path / "python")
    (tmp_path / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        mg,
        "musicgen_cfg",
        lambda: {
            "device": "auto",
            "ban_mps_on_abort": True,
            "request_timeout_sec": 30,
            "step_down_timeout_sec": 20,
            "model_id": "facebook/musicgen-large",
            "min_duration_sec": 4.0,
            "mmaudio_backup_on_stub": True,
        },
    )
    monkeypatch.setattr(mg, "cli_python_executable", lambda p: p)
    monkeypatch.setattr(mg, "effective_musicgen_device", lambda **kwargs: "mps")
    hub = tmp_path / "hf_cache" / "hub"
    for mid in (
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ):
        (hub / ("models--" + mid.replace("/", "--"))).mkdir(parents=True)
    monkeypatch.setattr(mg, "musicgen_hf_home", lambda: tmp_path / "hf_cache")

    devices: list[str] = []
    models: list[str] = []

    def fake_spawn(**kwargs):  # noqa: ANN003
        payload = json.loads(Path(str(kwargs["req"])).read_text())
        devices.append(str(payload.get("device")))
        models.append(str(payload.get("model_id")))
        return subprocess.CompletedProcess(kwargs["py"], -9, "", "timeout after 30s")

    monkeypatch.setattr(mg, "_spawn_musicgen", fake_spawn)
    out = tmp_path / "x.wav"
    prompt, neg = _succinct_prompts(role="theme_emphasis", palette_kind="stinger")
    mg.generate_music_clip(
        prompt=prompt,
        negative_prompt=neg,
        duration_sec=6.0,
        out_wav=out,
        role="theme_emphasis",
        seed=2,
    )
    assert models == [
        "facebook/musicgen-large",
        "facebook/musicgen-medium",
        "facebook/musicgen-small",
    ]
    assert devices == ["mps", "mps", "mps"]


# --- Live GPU probes --------------------------------------------------------


@pytest.mark.slow
def test_live_gpu_shipped_stinger_reports_winner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live: current defaults on MPS — large first; report which model wins."""
    if not _musicgen_ready("facebook/musicgen-large"):
        pytest.skip("MusicGen venv / large weights missing")
    if not (_hub_has("facebook/musicgen-medium") or _hub_has("facebook/musicgen-small")):
        pytest.skip("medium/small not cached")

    import interview_mux.musicgen_runner as mg

    monkeypatch.setenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "5")

    base = dict(mg.musicgen_cfg() or {})
    base.update(
        {
            "device": "auto",
            "model_id": "facebook/musicgen-large",
            "prefer_medium_on_cpu": False,
            "request_timeout_sec": 900,
            "cpu_request_timeout_sec": 180,
            "step_down_timeout_sec": 480,
            "mmaudio_backup_on_stub": False,
        }
    )
    monkeypatch.setattr(mg, "musicgen_cfg", lambda: base)

    assert effective_musicgen_device() == "mps"
    prompt, neg = _succinct_prompts(role="theme_emphasis", palette_kind="stinger")
    out = (
        repo_root()
        / "ASSETS"
        / "local_musicgen"
        / "probe"
        / "live_gpu_shipped_stinger.wav"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

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
    report = {
        "case": "shipped_large_ladder_gpu",
        "elapsed_sec": round(elapsed, 1),
        "effective_device_at_start": "mps",
        "device_used": meta.get("device"),
        "backend": meta.get("backend"),
        "winning_model_id": meta.get("model_id"),
        "fidelity_step": meta.get("fidelity_step"),
        "model_ladder": meta.get("model_ladder"),
        "musicgen_timeout": bool(meta.get("musicgen_timeout")),
        "musicgen_abort": bool(meta.get("musicgen_abort")),
        "musicgen_error": (meta.get("musicgen_error") or "")[:240] or None,
        "bytes": out.stat().st_size if out.is_file() else 0,
        "inspired_by": "exec_1765",
    }
    report_path = out.with_suffix(".ladder_report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== LIVE GPU shipped stinger ===")
    print(json.dumps(report, indent=2))

    assert out.is_file() and out.stat().st_size > 1000
    if report["backend"] == "musicgen":
        assert "musicgen" in str(report["winning_model_id"])
        assert str(report["device_used"]) in {"mps", "cpu"}
        assert (meta.get("model_ladder") or [])[:1] == ["facebook/musicgen-large"]
    else:
        assert report["backend"] == "musical_stub"


@pytest.mark.slow
def test_live_gpu_force_large_ladder_reports_which_step_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live diagnosis: does large fail on GPU, and which step-down wins?

    Mirrors the operator question from exec_1765, but on MPS with hang budgets
    so we do not sit 18+ minutes on a dead primary.
    """
    if not _musicgen_ready("facebook/musicgen-large"):
        pytest.skip("MusicGen venv / large weights missing")
    if not (_hub_has("facebook/musicgen-medium") and _hub_has("facebook/musicgen-small")):
        pytest.skip("medium/small not cached")

    import interview_mux.musicgen_runner as mg

    monkeypatch.setenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "5")

    base = dict(mg.musicgen_cfg() or {})
    base.update(
        {
            "device": "auto",
            "model_id": "facebook/musicgen-large",
            "prefer_medium_on_cpu": False,
            # Full ship-like primary budget (not the old 90s diagnosis cut).
            "request_timeout_sec": 900,
            "cpu_request_timeout_sec": 180,
            "step_down_timeout_sec": 480,
            "mmaudio_backup_on_stub": False,
        }
    )
    monkeypatch.setattr(mg, "musicgen_cfg", lambda: base)
    assert mg.effective_musicgen_device() == "mps"

    prompt, neg = _succinct_prompts(role="theme_emphasis", palette_kind="stinger")
    out = (
        repo_root()
        / "ASSETS"
        / "local_musicgen"
        / "probe"
        / "live_gpu_large_ladder_stinger.wav"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

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
    winner = str(meta.get("model_id") or "")
    step = str(meta.get("fidelity_step") or "")
    ladder = list(meta.get("model_ladder") or [])
    large_failed = (
        winner != "facebook/musicgen-large"
        or str(meta.get("backend")) != "musicgen"
        or bool(meta.get("musicgen_timeout"))
        or bool(meta.get("musicgen_abort"))
    )
    # If large won cleanly, large_failed is False.
    if winner == "facebook/musicgen-large" and meta.get("backend") == "musicgen":
        large_failed = False

    report = {
        "case": "force_large_ladder_gpu",
        "elapsed_sec": round(elapsed, 1),
        "effective_device_at_start": "mps",
        "device_used": meta.get("device"),
        "backend": meta.get("backend"),
        "large_failed_or_stepped_down": bool(
            winner != "facebook/musicgen-large" or meta.get("backend") != "musicgen"
        ),
        "winning_model_id": winner,
        "fidelity_step": step,
        "model_ladder": ladder,
        "musicgen_timeout": bool(meta.get("musicgen_timeout")),
        "musicgen_abort": bool(meta.get("musicgen_abort")),
        "musicgen_error": (meta.get("musicgen_error") or "")[:240] or None,
        "bytes": out.stat().st_size if out.is_file() else 0,
        "inspired_by": "exec_1765 large hang question",
    }
    report_path = out.with_suffix(".ladder_report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== LIVE GPU large→medium→small diagnosis ===")
    print(json.dumps(report, indent=2))
    # Keep lint happy — large_failed used for operator narrative via report.
    _ = large_failed

    assert out.is_file() and out.stat().st_size > 1000
    assert ladder[:1] == ["facebook/musicgen-large"]
    if meta.get("backend") == "musicgen":
        assert "musicgen" in winner
        assert step.startswith("ladder_")
    else:
        assert meta.get("backend") == "musical_stub"


@pytest.mark.slow
def test_live_gpu_cold_open_succinct_bed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live: 1765 cold_open role with succinct prompt + large-first ladder on MPS."""
    if not _musicgen_ready("facebook/musicgen-large"):
        pytest.skip("MusicGen venv / large weights missing")

    import interview_mux.musicgen_runner as mg

    monkeypatch.setenv("INTERVIEW_MUX_GPU_COOLDOWN_SEC", "5")

    base = dict(mg.musicgen_cfg() or {})
    base.update(
        {
            "device": "auto",
            "model_id": "facebook/musicgen-large",
            "request_timeout_sec": 900,
            "cpu_request_timeout_sec": 180,
            "step_down_timeout_sec": 480,
            "mmaudio_backup_on_stub": False,
        }
    )
    monkeypatch.setattr(mg, "musicgen_cfg", lambda: base)

    prompt, neg = _succinct_prompts(role="theme_cold_open", palette_kind="full_bed")
    assert len(prompt.split()) <= 80
    out = (
        repo_root()
        / "ASSETS"
        / "local_musicgen"
        / "probe"
        / "live_gpu_cold_open_bed.wav"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    meta = mg.generate_music_clip(
        prompt=prompt,
        negative_prompt=neg,
        duration_sec=8.0,
        out_wav=out,
        role="theme_cold_open",
        seed=1765,
    )
    elapsed = time.monotonic() - t0
    report = {
        "case": "cold_open_succinct_gpu_large_first",
        "elapsed_sec": round(elapsed, 1),
        "device_used": meta.get("device"),
        "backend": meta.get("backend"),
        "winning_model_id": meta.get("model_id"),
        "fidelity_step": meta.get("fidelity_step"),
        "model_ladder": meta.get("model_ladder"),
        "prompt_words": len(prompt.split()),
        "bytes": out.stat().st_size if out.is_file() else 0,
        "inspired_by": "exec_1765 show_theme_v2_cold_open",
    }
    out.with_suffix(".ladder_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("\n=== LIVE GPU cold_open bed ===")
    print(json.dumps(report, indent=2))

    assert out.is_file() and out.stat().st_size > 1000
    assert meta.get("backend") in {"musicgen", "musical_stub"}
    assert (meta.get("model_ladder") or [])[:1] == ["facebook/musicgen-large"]
