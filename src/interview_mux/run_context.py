from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import merged_config, repo_root
from interview_mux.file_store import read_json as fs_read_json
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.session_log import append_log

EXEC_ID_RE = re.compile(r"^exec_\d{3}_\d{8}T\d{6}Z$")
LEGACY_RUN_RE = re.compile(r"^run_\d{3}$")


class RunContext:
    def __init__(self, run_id: str | None = None, *, create: bool = True) -> None:
        cfg = merged_config()
        self.root = repo_root()
        self.assets_root = self.root / cfg.get("assets_root", "ASSETS")
        self.executions_root = self._executions_root(cfg)
        self.legacy_data_root = self.root / cfg.get("data_root", "data")
        self.run_id = run_id or self._allocate_run_id()
        self.run_dir = self._resolve_run_dir(self.run_id)
        if create:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            (self.run_dir / "vo_pickup").mkdir(exist_ok=True)
            (self.run_dir / ".stage_done").mkdir(exist_ok=True)

    @classmethod
    def exists(cls, run_id: str) -> bool:
        """True when the run directory exists (execution or legacy run_*)."""
        ctx = cls(run_id, create=False)
        return ctx.run_dir.is_dir()

    @staticmethod
    def _executions_root(cfg: dict[str, Any]) -> Path:
        rel = cfg.get("executions_root", "ASSETS/executions")
        p = Path(rel)
        if not p.is_absolute():
            p = repo_root() / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _resolve_run_dir(self, run_id: str) -> Path:
        if LEGACY_RUN_RE.match(run_id):
            return self.legacy_data_root / run_id
        return self.executions_root / run_id

    def _allocate_run_id(self) -> str:
        existing_nums: list[int] = []
        if self.executions_root.is_dir():
            for p in self.executions_root.iterdir():
                if not p.is_dir():
                    continue
                m = re.match(r"exec_(\d{3})_", p.name)
                if m:
                    existing_nums.append(int(m.group(1)))
        n = (max(existing_nums) + 1) if existing_nums else 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"exec_{n:03d}_{ts}"

    def path(self, *parts: str) -> Path:
        return self.run_dir.joinpath(*parts)

    def write_json(self, rel: str, data: Any) -> Path:
        if isinstance(data, dict):
            from interview_mux.prompt_validation import validate_artifact_write

            errors = validate_artifact_write(rel, data)
            if errors:
                raise ValueError(
                    f"{rel}: schema validation failed — " + "; ".join(errors[:6])
                )
        p = self.path(rel)
        fs_write_json(p, data)
        return p

    def read_json(self, rel: str) -> Any:
        p = self.path(rel)
        return fs_read_json(p)

    def init_run_meta(self, input_audio_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        meta_path = self.path("run_meta.json")
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            meta = self.read_json("run_meta.json")
        seq = self.run_id.split("_")[1] if self.run_id.startswith("exec_") else meta.get("execution_number")
        meta.setdefault("created_at", now)
        meta["updated_at"] = now
        meta["execution_number"] = int(seq) if seq else None
        meta["execution_id"] = self.run_id
        meta["input_audio_path"] = input_audio_path
        meta["storage_root"] = str(self.run_dir.relative_to(self.root))
        self.write_json("run_meta.json", meta)
        append_log(
            self.run_dir,
            f"Execution {self.run_id} initialized with input {input_audio_path}",
            level="info",
            stage="setup",
        )

    def log(self, message: str, *, level: str = "info", stage: str | None = None, detail: str | None = None) -> None:
        append_log(self.run_dir, message, level=level, stage=stage, detail=detail)
        meta_path = self.path("run_meta.json")
        if meta_path.is_file():
            meta = self.read_json("run_meta.json")
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.write_json("run_meta.json", meta)

    def mark_done(self, stage: str) -> None:
        marker = self.path(".stage_done", stage)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        self.log(f"Stage complete: {stage}", level="success", stage=stage)

    def is_done(self, stage: str) -> bool:
        return self.path(".stage_done", stage).is_file()

    def clear_from(self, stage: str, order: list[str]) -> None:
        if stage not in order:
            return
        idx = order.index(stage)
        for s in order[idx:]:
            marker = self.path(".stage_done", s)
            if marker.is_file():
                marker.unlink()
        self.log(f"Invalidated stages from {stage} onward — ready to re-run.", level="warning", stage=stage)

    def input_audio(self) -> Path:
        meta_path = self.path("run_meta.json")
        if meta_path.is_file():
            meta = self.read_json("run_meta.json")
            if meta.get("input_audio_path"):
                raw = Path(meta["input_audio_path"])
                if not raw.is_absolute():
                    raw = self.root / raw
                return raw
        cfg = merged_config()
        raw = Path(cfg["input_audio_path"])
        if not raw.is_absolute():
            raw = self.root / raw
        return raw

    def artifact_exists(self, rel: str) -> bool:
        return self.path(rel).is_file()

    @classmethod
    def list_runs(cls) -> list[str]:
        cfg = merged_config()
        root = repo_root()
        executions = cls._executions_root(cfg)
        legacy = root / cfg.get("data_root", "data")
        found: set[str] = set()
        for base in (executions, legacy):
            if not base.is_dir():
                continue
            for p in base.iterdir():
                if not p.is_dir():
                    continue
                if EXEC_ID_RE.match(p.name) or LEGACY_RUN_RE.match(p.name):
                    found.add(p.name)
        return sorted(found)

    @classmethod
    def summarize_run(cls, run_id: str) -> dict[str, Any]:
        ctx = cls(run_id, create=False)
        meta: dict[str, Any] = {}
        if ctx.artifact_exists("run_meta.json"):
            meta = ctx.read_json("run_meta.json")
        outputs: list[str] = []
        for rel in (
            "flow_1_master/master.wav",
            "flow_2_highlights/master.wav",
            "ingest/normalized.wav",
        ):
            if ctx.artifact_exists(rel):
                outputs.append(rel)
        return {
            "run_id": run_id,
            "execution_number": meta.get("execution_number"),
            "input_audio_path": meta.get("input_audio_path"),
            "selected_flow": meta.get("selected_flow"),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "storage_path": meta.get("storage_root") or str(ctx.run_dir.relative_to(ctx.root)),
            "analysis_complete": ctx.artifact_exists("analysis_complete.json"),
            "outputs": outputs,
        }
