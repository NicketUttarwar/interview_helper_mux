from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.assets_audio import ensure_wav_asset, repo_relative_path
from interview_mux.config import merged_config, repo_root
from filelock import FileLock

from interview_mux.file_store import lock_path_for
from interview_mux.file_store import read_json as fs_read_json
from interview_mux.file_store import write_json as fs_write_json
from interview_mux.session_log import append_log
from interview_mux.source_audio_hash import (
    compute_source_audio_hash,
    hashes_match,
    parse_hash_from_run_id,
)

EXEC_ID_RE = re.compile(r"^exec_\d{3,}(?:_[a-f0-9]{12})?_\d{8}T\d{6}Z$")
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

    @classmethod
    def _max_execution_number(cls, executions: Path) -> int:
        nums: list[int] = []
        if executions.is_dir():
            for p in executions.iterdir():
                if not p.is_dir():
                    continue
                m = re.match(r"exec_(\d+)_", p.name)
                if m:
                    nums.append(int(m.group(1)))
        return max(nums) if nums else 0

    @classmethod
    def allocate_run_id(cls, *, source_hash: str | None = None) -> str:
        cfg = merged_config()
        executions = cls._executions_root(cfg)
        counter_path = executions / ".execution_counter"
        with FileLock(lock_path_for(counter_path)):
            if counter_path.is_file():
                try:
                    n = int(counter_path.read_text(encoding="utf-8").strip()) + 1
                except ValueError:
                    n = cls._max_execution_number(executions) + 1
            else:
                n = cls._max_execution_number(executions) + 1
            counter_path.write_text(str(n), encoding="utf-8")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if source_hash:
            clean = re.sub(r"[^a-z0-9]", "", source_hash.lower())[:12]
            return f"exec_{n:03d}_{clean}_{ts}"
        return f"exec_{n:03d}_{ts}"

    def _allocate_run_id(self) -> str:
        return self.allocate_run_id()

    def path(self, *parts: str) -> Path:
        from interview_mux.write_staging import resolve_write_path

        rel = "/".join(parts)
        return resolve_write_path(self, rel)

    def read_path(self, *parts: str) -> Path:
        """Resolved path for reading a prior-stage artifact (not the active staging root)."""
        from interview_mux.write_staging import resolve_read_path

        rel = "/".join(parts)
        return resolve_read_path(self, rel)

    def artifact_path(self, rel: str) -> Path:
        """Alias for read_path — makes read intent obvious at call sites."""
        return self.read_path(*rel.split("/"))

    def write_json(
        self,
        rel: str,
        data: Any,
        *,
        stage_key: str | None = None,
        skip_handoff: bool = False,
    ) -> Path:
        prior_gap: Any = None
        prior_transitions: Any = None
        if rel == "understanding/gap_report.json" and isinstance(data, dict):
            try:
                if self.artifact_exists(rel):
                    prior_gap = self.read_json(rel)
            except Exception:
                prior_gap = None
        if rel == "master/transitions.json" and isinstance(data, dict):
            try:
                if self.artifact_exists(rel):
                    prior_transitions = self.read_json(rel)
            except Exception:
                prior_transitions = None
        if isinstance(data, dict):
            from interview_mux.artifact_writes import _prepare_for_disk_validation
            from interview_mux.edl_source_contract import prepare_edl_payload_for_disk
            from interview_mux.prompt_validation import validate_artifact_write

            data = prepare_edl_payload_for_disk(self, rel, data)
            payload = _prepare_for_disk_validation(data, rel_path=rel, stage_key=stage_key)
            # One-writer: admit hot authority JSON before schema so commit can harden
            # (e.g. music-only SDP inventory). Raw escape / nested admit skip this.
            try:
                from interview_mux.artifact_sanitize.one_writer import maybe_admit_hot_write

                admitted = maybe_admit_hot_write(
                    self,
                    rel,
                    payload,
                    stage_key=stage_key,
                    skip_handoff=skip_handoff,
                    write_committed=False,
                    reason=stage_key or "write_json",
                )
                if admitted is not None:
                    # Admit returns before the shared-path hook below — stamp now.
                    if (
                        stage_key
                        and isinstance(payload, dict)
                        and not getattr(self, "_shared_path_stamping", False)
                    ):
                        try:
                            from interview_mux.post_decision_sanitize import (
                                SHARED_PATH_CO_PRODUCERS,
                                after_shared_path_write,
                            )

                            if rel in SHARED_PATH_CO_PRODUCERS:
                                after_shared_path_write(self, rel, stage_key)
                        except Exception:
                            pass
                    return admitted
            except ImportError:
                pass
            errors = validate_artifact_write(rel, payload)
            if errors:
                raise ValueError(
                    f"{rel}: schema validation failed — " + "; ".join(errors[:6])
                )
            data = payload
        if skip_handoff:
            from interview_mux.write_staging import write_mirrored_json

            path = write_mirrored_json(self, rel, data)
        else:
            path = self.path(rel)
            fs_write_json(path, data)
            self._homunculus_admit_write(rel, data)
        # A-05: shared brief/boundaries/SDP — stamp authoritative_producer + reconcile.
        if (
            stage_key
            and isinstance(data, dict)
            and not getattr(self, "_shared_path_stamping", False)
        ):
            try:
                from interview_mux.post_decision_sanitize import (
                    SHARED_PATH_CO_PRODUCERS,
                    after_shared_path_write,
                )

                if rel in SHARED_PATH_CO_PRODUCERS:
                    after_shared_path_write(self, rel, stage_key)
            except Exception:
                pass
        if rel == "understanding/gap_report.json" and isinstance(data, dict):
            # VO5: suppress cascade while vo_synthesize holds the expensive lease.
            if int(getattr(self, "_vo_synth_lease", 0) or 0) > 0:
                pass
            else:
                try:
                    from interview_mux.vo_synthesis_audit import (
                        maybe_propagate_gap_spoken_text_change,
                        _SPOKEN_TEXT_CASCADE_STAGES,
                    )

                    maybe_propagate_gap_spoken_text_change(
                        self,
                        prior_report=prior_gap if isinstance(prior_gap, dict) else None,
                        new_report=data,
                        stage=stage_key or "gap_report_write",
                    )
                except Exception as exc:
                    consumers_done = False
                    try:
                        from interview_mux.vo_synthesis_audit import _SPOKEN_TEXT_CASCADE_STAGES

                        consumers_done = any(self.is_done(sid) for sid in _SPOKEN_TEXT_CASCADE_STAGES)
                    except Exception:
                        consumers_done = False
                    if consumers_done:
                        raise RuntimeError(
                            f"spoken text cascade failed (fail-closed; consumers exist): {exc}"
                        ) from exc
                    try:
                        self.log(
                            f"spoken text cascade failed (non-fatal): {exc}",
                            level="warning",
                            stage=stage_key or "gap_report_write",
                        )
                    except Exception:
                        pass
        if rel == "master/transitions.json" and isinstance(data, dict):
            try:
                from interview_mux.transition_vo import (
                    maybe_propagate_transitions_spoken_text_change,
                )

                maybe_propagate_transitions_spoken_text_change(
                    self,
                    prior_doc=prior_transitions
                    if isinstance(prior_transitions, dict)
                    else None,
                    new_doc=data,
                    stage=stage_key or "transitions_write",
                )
            except Exception as exc:
                try:
                    self.log(
                        f"transition spoken text cascade failed (non-fatal): {exc}",
                        level="warning",
                        stage=stage_key or "transitions_write",
                    )
                except Exception:
                    pass
        return path

    def _homunculus_admit_write(self, rel: str, data: Any) -> None:
        """0.1.0: every canonical write is admitted. Skip internal homunculus files."""
        if getattr(self, "_homunculus_persisting", False):
            return
        if rel.startswith("mastering/homunculus/") or rel in {"run_meta.json", "gui_job.json"}:
            return
        try:
            from interview_mux.homunculus.issues import is_homunculus_meta
            from interview_mux.homunculus.admit import admit

            if not is_homunculus_meta(self):
                return
            admit(
                self,
                identity=f"write:{rel}",
                action="keep",
                payload=data if isinstance(data, dict) else {"rel": rel},
                fact_id=f"write:{rel}",
            )
        except Exception:
            return

    def read_json(self, rel: str) -> Any:
        from interview_mux.write_staging import resolve_read_path

        p = resolve_read_path(self, rel)
        data = fs_read_json(p)
        consumer = getattr(self, "_lifecycle_consumer_stage", None)
        if consumer:
            from interview_mux.artifact_lifecycle import read_stale_guard

            stale = read_stale_guard(self, rel, consumer_stage=str(consumer))
            if stale:
                raise ValueError(stale)
        return data

    def artifact_exists_required(
        self,
        rel: str,
        *,
        stage: str | None = None,
        label: str | None = None,
    ) -> None:
        """Raise FileNotFoundError when a required artifact is missing."""
        if self.artifact_exists(rel):
            return
        from interview_mux.operator_trace import log_step, resolve_stage
        from interview_mux.write_staging import staging_approval_hint, staging_read_trap_hint

        desc = label or rel
        sid = resolve_stage(stage)
        msg = f"Required artifact missing: {desc}"
        hint = staging_approval_hint(self, rel) or staging_read_trap_hint(self, rel)
        if hint:
            msg = f"{msg}. {hint}"
        log_step(
            msg,
            ctx=self,
            stage=sid,
            level="error",
            detail={
                "event": "missing_artifact",
                "path": rel,
                "journey_kind": "execute",
                "remediation": hint,
            },
        )
        raise FileNotFoundError(f"{msg} ({rel})")

    def read_artifact_path(self, rel: str, *, stage: str | None = None, label: str | None = None) -> Path:
        """Verify artifact exists and return the resolved read path (never the active staging root)."""
        self.artifact_exists_required(rel, stage=stage, label=label)
        p = self.read_path(*rel.split("/"))
        if not p.is_file():
            raise FileNotFoundError(f"Required artifact not readable: {label or rel} ({p})")
        return p

    def read_json_required(
        self,
        rel: str,
        *,
        stage: str | None = None,
        label: str | None = None,
    ) -> Any:
        """Read JSON after verifying the artifact exists."""
        self.artifact_exists_required(rel, stage=stage, label=label)
        return self.read_json(rel)

    def write_json_validated(
        self,
        rel: str,
        data: Any,
        *,
        stage_key: str | None = None,
        skip_handoff: bool = False,
    ) -> Path:
        """Write JSON with schema validation (delegates to write_json)."""
        return self.write_json(rel, data, stage_key=stage_key, skip_handoff=skip_handoff)

    def init_run_meta(
        self,
        input_audio_path: str,
        *,
        source_audio_hash: str | None = None,
        source_audio_hash_short: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        meta_path = self.final_path("run_meta.json")
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            meta = fs_read_json(meta_path)
        seq = self.run_id.split("_")[1] if self.run_id.startswith("exec_") else meta.get("execution_number")
        meta.setdefault("created_at", now)
        meta["updated_at"] = now
        meta["execution_number"] = int(seq) if seq and str(seq).isdigit() else meta.get("execution_number")
        meta["execution_id"] = self.run_id
        resolved_input = self._resolve_input_audio_ref(input_audio_path)
        original_stored = repo_relative_path(self.root, resolved_input)
        wav_input = ensure_wav_asset(resolved_input)
        stored_input = repo_relative_path(self.root, wav_input)
        meta["input_audio_path"] = stored_input
        # Preserve the operator-selected file when we converted mp3/mp4/etc. → wav.
        if wav_input.resolve() != resolved_input.resolve():
            meta["input_audio_path_original"] = original_stored
        else:
            meta.pop("input_audio_path_original", None)
        if source_audio_hash and source_audio_hash_short:
            meta["source_audio_hash"] = source_audio_hash
            meta["source_audio_hash_short"] = source_audio_hash_short
        else:
            from interview_mux.source_audio_hash import source_audio_hash_pair

            full, short = source_audio_hash_pair(wav_input)
            meta["source_audio_hash"] = full
            meta["source_audio_hash_short"] = short
        meta["storage_root"] = str(self.run_dir.relative_to(self.root))
        fs_write_json(meta_path, meta)
        log_msg = f"Execution {self.run_id} initialized with input {stored_input}"
        if wav_input != resolved_input.resolve():
            log_msg = (
                f"Execution {self.run_id} initialized with input {stored_input} "
                f"(converted from {input_audio_path})"
            )
        append_log(self.run_dir, log_msg, level="info", stage="setup")

    def mutate_run_meta(self, mutator: Any) -> dict[str, Any]:
        """Locked read-modify-write for run_meta.json (avoids concurrent field loss)."""
        meta_path = self.final_path("run_meta.json")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(lock_path_for(meta_path)):
            meta: dict[str, Any] = {}
            if meta_path.is_file():
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                meta = raw if isinstance(raw, dict) else {}
            mutator(meta)
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
            tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(meta_path)
        return meta

    def log(
        self,
        message: str,
        *,
        level: str = "info",
        stage: str | None = None,
        detail: str | dict[str, Any] | None = None,
        action_id: str | None = None,
        origin: str | None = None,
    ) -> None:
        from interview_mux.operator_log import operator_log

        operator_log(
            message,
            run_dir=self.run_dir,
            level=level,
            stage=stage,
            detail=detail,
            action_id=action_id,
            origin=origin,  # type: ignore[arg-type]
        )

    def log_handoff(self, stage_id: str, paths: list[str], *, audit_path: str | None = None) -> None:
        """Operator-visible file handoff after a stage completes."""
        from interview_mux.web.stages import STAGE_BY_ID

        if not paths and not audit_path:
            return
        committed: list[str] = []
        pending_only: list[str] = []
        for p in paths:
            final = self.final_path(*str(p).replace("\\", "/").split("/"))
            if final.is_file():
                committed.append(p)
            elif self.artifact_exists(p):
                pending_only.append(p)
        present = committed or [p for p in paths if self.artifact_exists(p)]
        info = STAGE_BY_ID.get(stage_id)
        title = info.title if info else stage_id
        payload: dict[str, Any] = {
            "handoff": present or paths,
            "committed": committed,
            "pending": pending_only,
        }
        if audit_path and self.artifact_exists(audit_path):
            payload["audit_path"] = audit_path
        self.log(
            f"{title} complete — review outputs before continuing",
            level="success",
            stage=stage_id,
            detail=payload,
        )
        meta_path = self.path("run_meta.json")
        if meta_path.is_file():
            meta = self.read_json("run_meta.json")
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.write_json("run_meta.json", meta)

    def _latest_stage_audit(self, stage: str) -> str | None:
        audit_dir = self.path("understanding", "stage_runs", stage)
        if not audit_dir.is_dir():
            return None
        attempts = sorted(audit_dir.glob("attempt_*.json"))
        if not attempts:
            return None
        return str(attempts[-1].relative_to(self.run_dir)).replace("\\", "/")

    def mark_done(self, stage: str, *, force: bool = False) -> None:
        from interview_mux.write_staging import (
            has_pending_writes,
            record_pending_approval,
            write_approval_enabled,
        )

        # TH1b: any force=True (except _mark_done_raw escape) routes through heal.
        if force and not getattr(self, "_mark_done_raw", False):
            from interview_mux.stage_completion import heal_or_refuse_mark

            heal_or_refuse_mark(self, stage, force=True)
            return

        if (
            not force
            and write_approval_enabled()
            and has_pending_writes(self, stage)
        ):
            record_pending_approval(self, stage)
            return

        from interview_mux.prompt_validation import STAGE_ARTIFACT_DISK_PATHS
        from interview_mux.artifact_completeness import artifact_status
        from interview_mux.v2.config import ALL_LLM_STAGES

        # Fixture hollow-stamp (`_mark_done_raw`) bypasses disk/semantic completeness —
        # heal_or_refuse / FORCE_DONE_GUARDED gate real force marks instead.
        raw_stamp = bool(getattr(self, "_mark_done_raw", False))

        rel = STAGE_ARTIFACT_DISK_PATHS.get(stage)
        if rel and not raw_stamp:
            if self.artifact_exists(rel):
                st = artifact_status(rel, self)
                if st != "complete":
                    self.log(
                        f"Refusing mark_done({stage}{', force' if force else ''}): "
                        f"{rel} is {st}",
                        level="warning",
                        stage=stage,
                    )
                    return
            elif not force and stage in ALL_LLM_STAGES:
                self.log(
                    f"Refusing mark_done({stage}): required artifact {rel} missing",
                    level="warning",
                    stage=stage,
                )
                return

        # Hollow delivery producers: non-force marks still refuse incompleteness.
        # Force hollow-stamp is gated solely by heal_or_refuse_mark /
        # assert_may_force_done (FORCE_DONE_GUARDED includes junction_snip_qa).
        try:
            from interview_mux.thrash_hardening import FORCE_DONE_GUARDED
            from interview_mux.stage_completion import stage_artifact_incompleteness

            if stage in FORCE_DONE_GUARDED and not force and not raw_stamp:
                hollow = stage_artifact_incompleteness(self, stage)
                if hollow:
                    skip_stub = False
                    try:
                        from interview_mux.gates import g1_vo_was_skipped_optional

                        if stage in {
                            "vo_synthesize",
                            "vo_line_adjudicate",
                        } and g1_vo_was_skipped_optional(self):
                            skip_stub = True
                    except Exception:
                        pass
                    if not skip_stub:
                        self.log(
                            f"Refusing mark_done({stage}): {hollow}",
                            level="warning",
                            stage=stage,
                            detail={"hollow_reason": hollow},
                        )
                        return
        except Exception:
            pass

        marker = self.final_path(".stage_done", stage)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        if stage == "mix":
            try:

                def _clear_seating_stale(meta: dict[str, Any]) -> None:
                    meta.pop("assembly_seating_stale", None)
                    meta.pop("assembly_seating_stale_reason", None)

                if self.artifact_exists("run_meta.json"):
                    self.mutate_run_meta(_clear_seating_stale)
            except Exception:
                pass
        # Do NOT discard .pending_writes here. mark_done often runs before
        # after_stage_write_check flush (ingest, nested stages). Flush already
        # promotes then rmtree; pre-flush discard ate unflushed WAVs.
        from interview_mux.web.stages import STAGE_BY_ID

        def _clear_handoff_pending(meta: dict[str, Any]) -> None:
            pending_writes = dict(meta.get("handoff_pending_writes") or {})
            pending_writes.pop(stage, None)
            meta["handoff_pending_writes"] = pending_writes

        if self.artifact_exists("run_meta.json"):
            self.mutate_run_meta(_clear_handoff_pending)

        info = STAGE_BY_ID.get(stage)
        paths = list(info.artifacts) if info else []
        self.log_handoff(stage, paths, audit_path=self._latest_stage_audit(stage))
        from interview_mux.web.run_snapshot_cache import invalidate_run_snapshot

        invalidate_run_snapshot(self.run_id)
        self.bump_snapshot_version()

    def bump_snapshot_version(self) -> int:
        if not self.artifact_exists("run_meta.json"):
            return 0

        def _patch(meta: dict[str, Any]) -> None:
            meta["snapshot_version"] = int(meta.get("snapshot_version") or 0) + 1

        meta = self.mutate_run_meta(_patch)
        from interview_mux.web.run_snapshot_cache import invalidate_run_snapshot

        invalidate_run_snapshot(self.run_id)
        return int(meta.get("snapshot_version") or 0)

    def is_done(self, stage: str) -> bool:
        return self.final_path(".stage_done", stage).is_file()

    @staticmethod
    def _combined_clear_allowed() -> bool:
        """Pytest-only escape — production / normal CLI must never bypass.

        Requires both an explicit hatch (env or class flag) **and** an active
        pytest session (``PYTEST_CURRENT_TEST``). Accidental ``MUX_ALLOW_COMBINED_CLEAR=1``
        in a forensics shell will not reopen nuclear clears.
        """
        if not str(os.environ.get("PYTEST_CURRENT_TEST") or "").strip():
            return False
        if os.environ.get("MUX_ALLOW_COMBINED_CLEAR", "").strip() == "1":
            return True
        return bool(getattr(RunContext, "_ALLOW_COMBINED_CLEAR", False))

    @staticmethod
    def _is_combined_pipeline_order(order: list[str]) -> bool:
        """True when ``order`` mixes ANALYSIS_ORDER and DELIVERY_ORDER stages."""
        try:
            from interview_mux.v2.config import ANALYSIS_ORDER, DELIVERY_ORDER
        except Exception:
            return False
        analysis = set(ANALYSIS_ORDER)
        delivery = set(DELIVERY_ORDER)
        seen = set(order)
        return bool(seen & analysis) and bool(seen & delivery)

    def _refuse_combined_pipeline_order(self, order: list[str]) -> None:
        if not self._is_combined_pipeline_order(order):
            return
        if self._combined_clear_allowed():
            return
        raise ValueError(
            "combined ANALYSIS+DELIVERY clear_from forbidden; "
            "use apply_bounded_invalidation or single-order operator clear"
        )

    def clear_from(
        self, stage: str, order: list[str], *, blast_source: str | None = None
    ) -> None:
        if stage not in order:
            return
        self._refuse_combined_pipeline_order(order)
        from interview_mux.execution_invalidation import (
            archive_artifacts_from,
            clear_pending_writes_from,
        )
        from interview_mux.artifact_lifecycle import invalidate_downstream_memory
        from interview_mux.delivery_guardrails import (
            INVALIDATION_BLAST_RADIUS,
            invalidation_allowed_downstream,
            music_clear_blocked,
        )

        source = str(blast_source or stage).strip() or stage
        idx = order.index(stage)
        candidates = list(order[idx:])
        restricted = source in INVALIDATION_BLAST_RADIUS
        music_protected = any(
            music_clear_blocked(self, s, source=source) for s in candidates
        )
        to_clear = [
            s
            for s in candidates
            if (
                s == stage
                or invalidation_allowed_downstream(source, s)
            )
            and not music_clear_blocked(self, s, source=source)
        ]
        # When music epoch is sealed, never full-archive (would wipe theme WAVs).
        if not restricted and not music_protected:
            archive_artifacts_from(self, stage, order)
            invalidate_downstream_memory(self, stage)
            clear_pending_writes_from(self, stage, order)
        else:
            # Restricted blast or sealed music: marker-only for allowed set.
            invalidate_downstream_memory(self, stage)
            if not music_protected:
                clear_pending_writes_from(self, stage, order)
        for s in to_clear:
            marker = self.final_path(".stage_done", s)
            if marker.is_file():
                marker.unlink()
        from interview_mux.gap_fill_eligibility import maybe_clear_gap_fill_skip_on_invalidation

        maybe_clear_gap_fill_skip_on_invalidation(self, stage)
        from interview_mux.stage_step_through import clear_step_through_from

        clear_step_through_from(self, stage, order)
        from interview_mux.refinement_ledger import reset_ledger_from_stages

        reset_ledger_from_stages(self, set(to_clear))
        kept = len(candidates) - len(to_clear)
        self.log(
            f"Invalidated stages from {stage} onward"
            + (f" (blast={source}, kept={kept})" if restricted or kept else "")
            + " — ready to re-run.",
            level="warning",
            stage=stage,
        )

    def _resolve_input_audio_ref(self, input_audio_path: str) -> Path:
        raw = Path(input_audio_path)
        if not raw.is_absolute():
            raw = self.root / raw
        return raw

    def input_audio(self) -> Path:
        meta_path = self.path("run_meta.json")
        if meta_path.is_file():
            meta = self.read_json("run_meta.json")
            if meta.get("input_audio_path"):
                return ensure_wav_asset(self._resolve_input_audio_ref(meta["input_audio_path"]))
        cfg = merged_config()
        raw = Path(cfg["input_audio_path"])
        if not raw.is_absolute():
            raw = self.root / raw
        return ensure_wav_asset(raw)

    def source_audio_hash(self, *, recompute: bool = False) -> str | None:
        """Full SHA-256 of pipeline WAV from run_meta, or None."""
        if not self.artifact_exists("run_meta.json"):
            return None
        meta = self.read_json("run_meta.json")
        if not isinstance(meta, dict):
            return None
        if recompute and meta.get("input_audio_path"):
            try:
                wav = ensure_wav_asset(self._resolve_input_audio_ref(meta["input_audio_path"]))
                live = compute_source_audio_hash(wav)
                stored = meta.get("source_audio_hash")
                if stored and not hashes_match(str(stored), live):
                    self.log(
                        "Source audio file changed since run init — stored hash no longer matches.",
                        level="warning",
                        stage="setup",
                        detail={"stored_hash": stored, "live_hash": live},
                    )
                return live
            except (FileNotFoundError, OSError):
                return None
        if meta.get("source_audio_hash"):
            return str(meta["source_audio_hash"])
        if meta.get("input_audio_path"):
            try:
                wav = ensure_wav_asset(self._resolve_input_audio_ref(meta["input_audio_path"]))
                return compute_source_audio_hash(wav)
            except (FileNotFoundError, OSError):
                return None
        return None

    def artifact_exists(self, rel: str) -> bool:
        from interview_mux.write_staging import artifact_exists_resolved

        return artifact_exists_resolved(self, rel)

    def final_path(self, *parts: str) -> Path:
        """Absolute final on-disk path (never staging)."""
        return self.run_dir.joinpath(*parts)

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
            "master/master.wav",
            "ingest/normalized.wav",
        ):
            if ctx.artifact_exists(rel):
                outputs.append(rel)
        hash_short = meta.get("source_audio_hash_short") or parse_hash_from_run_id(run_id)
        halt_plan = None
        if ctx.artifact_exists("mastering/homunculus/plan.json"):
            try:
                halt_plan = ctx.read_json("mastering/homunculus/plan.json")
            except Exception:
                halt_plan = None
        return {
            "run_id": run_id,
            "execution_number": meta.get("execution_number"),
            "input_audio_path": meta.get("input_audio_path"),
            "source_audio_hash": meta.get("source_audio_hash") or ctx.source_audio_hash(),
            "source_audio_hash_short": hash_short,
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "storage_path": meta.get("storage_root") or str(ctx.run_dir.relative_to(ctx.root)),
            "working_dir": str(ctx.run_dir),
            "analysis_complete": ctx.artifact_exists("analysis_complete.json"),
            "outputs": outputs,
            "homunculus_version": meta.get("homunculus_version") or "0.0.0",
            "homunculus_halt_plan": halt_plan,
            "podcast_id": meta.get("podcast_id"),
            "podcast_title": meta.get("podcast_title"),
        }
