"""E2E session orchestrator."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from e2e_runner.api_client import ApiClient
from e2e_runner.browser_driver import BrowserDriver
from e2e_runner.exceptions import E2EFailure, E2EHealExhausted, E2EStall
from e2e_runner.failure_bundle import write_failure_bundle
from e2e_runner.final_report import write_final_report
from e2e_runner.gate_handlers import execute_with_consent, resolve_blocking
from e2e_runner.heal import run_heal
from e2e_runner.journey_driver import decide_next_step, fingerprint
from e2e_runner.server_lifecycle import ServerProcess
from e2e_runner.stall_detector import StallDetector
from e2e_runner.types import IncidentRecord, SessionConfig, StepKind
from e2e_runner.verify import verify_flow


class Orchestrator:
    def __init__(self, cfg: SessionConfig) -> None:
        self.cfg = cfg
        self.repo_root = Path(cfg.repo_root)
        self.log_dir = Path(cfg.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = datetime.now(timezone.utc)
        self.incidents: list[IncidentRecord] = []
        self.run_ids: list[str] = []
        self.clean_flows: list[str] = []
        self.residual: list[str] = []
        self._incident_counter = 0
        self._heal_counts: dict[str, int] = {}

    def run(self) -> int:
        input_path = self.repo_root / self.cfg.input_audio
        if not input_path.is_file():
            self.residual.append(f"Missing input audio: {input_path}")
            self._write_report("failed")
            return 1

        server = ServerProcess(self.repo_root)
        api: ApiClient | None = None
        browser: BrowserDriver | None = None
        exit_code = 0

        try:
            server.start(fresh_session=self.cfg.resume_run_id is None)
            api = ApiClient(self.cfg.base_url)
            api.wait_for_health()

            browser = BrowserDriver(self.cfg.base_url, headless=self.cfg.headless)
            browser.start()

            if self.cfg.resume_run_id:
                api.set_active(self.cfg.resume_run_id)
                flows = self.cfg.flows
            else:
                flows = self.cfg.flows

            for flow in flows:
                try:
                    run_id = self._run_flow(server, api, browser, flow)
                    if run_id:
                        self.run_ids.append(run_id)
                        ok, msg = verify_flow(self.repo_root, run_id, flow)
                        if ok:
                            self.clean_flows.append(flow)
                        else:
                            self._handle_failure(
                                server,
                                api,
                                browser,
                                failure_type="verify",
                                summary=f"{flow} verification failed",
                                run=api.get_run(run_id) if run_id else None,
                                exc=E2EFailure(msg),
                            )
                except E2EHealExhausted as exc:
                    self.residual.append(str(exc))
                    exit_code = 1
                    break
                except (E2EFailure, E2EStall) as exc:
                    if not self._handle_failure(
                        server,
                        api,
                        browser,
                        failure_type=type(exc).__name__,
                        summary=str(exc),
                        run=None,
                        exc=exc,
                    ):
                        exit_code = 1
                        break

            outcome = "passed" if exit_code == 0 and not self.residual else (
                "partial" if self.clean_flows else "failed"
            )
            self._write_report(outcome)
            return exit_code
        finally:
            if browser:
                browser.stop()
            if api:
                api.close()
            server.stop()

    def _run_flow(
        self,
        server: ServerProcess,
        api: ApiClient,
        browser: BrowserDriver,
        flow: str,
    ) -> str | None:
        if self.cfg.resume_run_id and flow == self.cfg.flows[0]:
            run_id = self.cfg.resume_run_id
            api.set_active(run_id)
            self.cfg.resume_run_id = None
        else:
            asset_path = self.cfg.input_audio
            created = api.create_run(asset_path, flow_intent=flow)
            run_id = str(created.get("run_id") or "")
            api.set_active(run_id)
            basename = Path(asset_path).name
            browser.start_execution(basename, flow)

        stall = StallDetector()
        job_running = False

        while True:
            run = api.get_run(run_id)
            job = api.get_job(run_id)
            run["job"] = job
            step = decide_next_step(
                run,
                flow=flow,
                until_stage=self.cfg.until_stage,
                job_running=job_running,
            )

            fp = fingerprint(run)
            stall.observe(fp, job_running=job_running)
            stuck, reason = stall.is_stuck(job_running=job_running)
            if stuck:
                raise E2EStall(reason)

            if step.kind == StepKind.DONE:
                return run_id

            if step.kind == StepKind.VERIFY_FLOW:
                return run_id

            if step.kind == StepKind.RESOLVE_GATE:
                browser.open_checkpoint()
                actions = resolve_blocking(api, run_id, run)
                if not actions:
                    browser.complete_transcript_review()
                    browser.select_flow(flow)
                    browser.mark_profile_verified()
                    browser.grant_api_consent()
                    actions = resolve_blocking(api, run_id, api.get_run(run_id))
                browser.checkpoint_continue()
                stall.reset()
                time.sleep(self.cfg.poll_interval_s)
                continue

            if step.kind == StepKind.EXECUTE and step.execute_body:
                if not browser.click_journey_cta():
                    execute_with_consent(api, run_id, step.execute_body)
                job_running = True
                job = api.wait_for_job_terminal(run_id, poll_s=self.cfg.poll_interval_s)
                job_running = False
                run["job"] = job
                if str(job.get("status")) == "error":
                    raise E2EFailure(str(job.get("message") or job.get("error")))
                stall.reset()
                time.sleep(self.cfg.poll_interval_s)
                continue

            if step.kind == StepKind.WAIT:
                if step.detail.startswith("error:"):
                    raise E2EFailure(step.detail)
                time.sleep(self.cfg.poll_interval_s)
                continue

            time.sleep(self.cfg.poll_interval_s)

    def _handle_failure(
        self,
        server: ServerProcess,
        api: ApiClient,
        browser: BrowserDriver,
        *,
        failure_type: str,
        summary: str,
        run: dict | None,
        exc: Exception,
    ) -> bool:
        self._incident_counter += 1
        iid = self._incident_counter
        run_id = str((run or {}).get("run_id") or self.cfg.resume_run_id or "")
        log_tail = api.get_log(run_id) if run_id else []

        shot = self.log_dir / "failures" / f"{iid:03d}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        try:
            browser.screenshot(str(shot))
        except Exception:
            shot = None

        bundle = write_failure_bundle(
            self.log_dir,
            repo_root=self.repo_root,
            incident_id=iid,
            failure_type=failure_type,
            summary=summary,
            run=run,
            log_tail=log_tail,
            screenshot_path=str(shot) if shot else None,
        )

        heal_key = f"{run_id}:{summary[:80]}"
        attempts = self._heal_counts.get(heal_key, 0)
        if not self.cfg.heal_enabled or attempts >= self.cfg.max_heal_attempts:
            self.incidents.append(
                IncidentRecord(
                    incident_id=iid,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    elapsed_s=(datetime.now(timezone.utc) - self.started_at).total_seconds(),
                    failure_type=failure_type,
                    summary=summary,
                    run_id=run_id or None,
                    flow=(run or {}).get("flow_intent"),
                    phase=((run or {}).get("journey") or {}).get("phase"),
                    next_action=((run or {}).get("journey") or {}).get("next_action"),
                    stage_id=None,
                    symptom=str(exc),
                    root_cause=summary,
                    severity="major",
                    bundle_path=str(bundle),
                )
            )
            if attempts >= self.cfg.max_heal_attempts:
                raise E2EHealExhausted(f"Max heal attempts for {heal_key}")
            return False

        self._heal_counts[heal_key] = attempts + 1
        heal = run_heal(
            self.repo_root,
            self.log_dir,
            incident_id=iid,
            failure_summary=summary,
            run_id=run_id or None,
            run_snapshot=run,
            log_tail=log_tail,
            api_key=os.environ.get("CURSOR_API_KEY"),
        )

        self.incidents.append(
            IncidentRecord(
                incident_id=iid,
                timestamp=datetime.now(timezone.utc).isoformat(),
                elapsed_s=(datetime.now(timezone.utc) - self.started_at).total_seconds(),
                failure_type=failure_type,
                summary=summary,
                run_id=run_id or None,
                flow=(run or {}).get("flow_intent"),
                phase=((run or {}).get("journey") or {}).get("phase"),
                next_action=((run or {}).get("journey") or {}).get("next_action"),
                stage_id=None,
                symptom=str(exc),
                root_cause=summary if not heal.success else "Addressed by agent heal",
                severity="major" if not heal.success else "minor",
                fix_applied=heal.summary,
                files_changed=heal.files_changed,
                verification="pytest passed" if heal.pytest_ok else "pytest failed",
                bundle_path=str(bundle),
                heal_transcript_path=heal.transcript_path,
            )
        )

        if heal.success:
            server.restart(fresh_session=False)
            api.wait_for_health()
            browser.page.goto(self.cfg.base_url) if browser.page else None
            if run_id:
                api.set_active(run_id)
            return True

        return False

    def _write_report(self, outcome: str) -> None:
        session_id = self.log_dir.name.replace("session_", "")
        write_final_report(
            session_id=session_id,
            log_dir=self.log_dir,
            repo_root=self.repo_root,
            input_audio=self.cfg.input_audio,
            flows=self.cfg.flows,
            outcome=outcome,
            run_ids=self.run_ids,
            incidents=self.incidents,
            clean_flows=self.clean_flows,
            residual=self.residual,
            started_at=self.started_at,
            ended_at=datetime.now(timezone.utc),
        )
