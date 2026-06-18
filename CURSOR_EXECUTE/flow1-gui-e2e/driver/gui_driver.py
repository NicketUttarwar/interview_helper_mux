#!/usr/bin/env python3
"""Playwright driver for Flow 1 GUI end-to-end automation."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

_DRIVER_DIR = Path(__file__).resolve().parent
_CAMPAIGN_DIR = _DRIVER_DIR.parent
_REPO_ROOT = _CAMPAIGN_DIR.parent.parent

if str(_DRIVER_DIR) not in sys.path:
    sys.path.insert(0, str(_DRIVER_DIR))

from api_client import ApiClient  # noqa: E402
from execution_screenshots import ExecutionScreenshotArchive  # noqa: E402
from gate_handlers import (  # noqa: E402
    baseline_run_ids_for_wav,
    extract_run_id_from_page,
    resolve_gates,
    resolve_run_id_after_start,
    wait_for_gui_run_loaded,
    wait_for_start_tab_ready,
)
from logging_banner import EventLogger  # noqa: E402
from state import DriverState, default_state_path  # noqa: E402

EXIT_OK = 0
EXIT_BLOCKER = 2
EXIT_ERROR = 1


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def master_path(repo_root: Path, run_id: str) -> Path:
    return repo_root / "ASSETS" / "executions" / run_id / "flow_1_master" / "master.wav"


def write_blocker(
    campaign_dir: Path,
    *,
    slug: str,
    run_id: str | None,
    stage: str | None,
    job_status: str | None,
    symptom: str,
    screenshot: Path | None,
    log_tail: list[dict],
) -> Path:
    blockers = campaign_dir / "blockers"
    blockers.mkdir(parents=True, exist_ok=True)
    existing = sorted(blockers.glob("BLOCKER-*.md"))
    n = len(existing) + 1
    path = blockers / f"BLOCKER-{n:03d}-{slug}.md"
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# BLOCKER-{n:03d} — {slug}",
        "",
        "- **Status:** open",
        f"- **Detected at:** {ts}",
        f"- **run_id:** {run_id or 'unknown'}",
        f"- **stage:** {stage or 'unknown'}",
        f"- **job_status:** {job_status or 'unknown'}",
        f"- **Screenshot:** {screenshot or 'none'}",
        "",
        "## Symptom",
        "",
        symptom,
        "",
        "## gui_log tail",
        "",
    ]
    for entry in log_tail[-20:]:
        lines.append(f"- `{entry.get('ts', '')}` {entry.get('message', '')}")
    lines.extend(
        [
            "",
            "## Root cause",
            "",
            "(pending E2E-03)",
            "",
            "## Fix",
            "",
            "(pending E2E-03)",
            "",
            "## Fix comment",
            "",
            "(pending E2E-03)",
            "",
            "## Resume",
            "./CURSOR_EXECUTE/flow1-gui-e2e/run.sh --resume",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _clear_blocking_session(page, log: EventLogger, archive: ExecutionScreenshotArchive | None) -> None:
    """Dismiss recovery / locked-session views so Start tab assets are reachable."""
    recovery = page.get_by_role("heading", name="Session recovery")
    if recovery.count():
        clear_btn = page.get_by_role("button", name="Clear session", exact=True)
        if clear_btn.count() and clear_btn.first.is_enabled():
            log.action("Clearing stale session (recovery view)")
            clear_btn.first.click()
            if archive:
                archive.maybe_capture_after_click(page, "click:clear-session")
            page.wait_for_timeout(1500)
        return
    locked = page.get_by_role("heading", name="Session in progress")
    if locked.count():
        log.action("Session already locked — opening Pipeline (resume path)")
        cont = page.get_by_role("button", name="Continue in Pipeline", exact=True)
        if cont.count():
            cont.first.click()
            page.wait_for_timeout(1000)


def start_run(
    page,
    log: EventLogger,
    config: dict,
    wav_name: str,
    archive: ExecutionScreenshotArchive | None,
    *,
    api: ApiClient | None = None,
) -> set[str]:
    """Open Start tab, wait for session, click Start; return baseline run_ids for this WAV."""
    log.step("DRIVER", "Opening Start tab")
    page.goto(config["base_url"], wait_until="domcontentloaded", timeout=60_000)
    start_tab = page.get_by_role("button", name="Start", exact=True)
    if start_tab.count():
        start_tab.first.click()
        if archive:
            archive.maybe_capture_after_click(page, "click:tab-Start")

    asset_tid = f"start-asset-{wav_name}"
    exec_tid = f"start-execution-{wav_name}"
    log.action(f"Waiting for data-testid={asset_tid}")
    page.get_by_test_id(asset_tid).first.wait_for(state="visible", timeout=120_000)

    _clear_blocking_session(page, log, archive)

    log.action("Waiting for Start tab session boot (start-tab-ready)")
    wait_for_start_tab_ready(page, exec_tid, timeout_s=120, log=log)

    baseline: set[str] = set()
    if api is not None:
        try:
            baseline = baseline_run_ids_for_wav(list(api.runs().get("runs") or []), wav_name)
        except Exception:
            baseline = set()

    if page.get_by_test_id("flow-intent-flow1").count():
        log.action("Selecting flow intent flow1")
        page.get_by_test_id("flow-intent-flow1").first.click()
        if archive:
            archive.maybe_capture_after_click(page, "click:flow-intent-flow1")

    log.action(f"Clicking data-testid={exec_tid}")
    page.get_by_test_id(exec_tid).first.click(timeout=15_000)
    if archive:
        archive.maybe_capture_after_click(page, f"click:{exec_tid}")
    page.wait_for_timeout(3000)
    return baseline


def screenshot(page, session_dir: Path, name: str) -> Path:
    shots = session_dir / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    path = shots / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def dry_run_journey(log: EventLogger) -> None:
    log.step("DRY-RUN", "Planned GUI journey (no browser)")
    phases = [
        "START: flow-intent-flow1 + start-execution",
        "PREPARE: ingest through G0/G0.5",
        "ANALYZE: source_acoustic_profile through optimal_questions + profile",
        "G1/G2: VO upload + flow1 select",
        "BUILD: topic_coverage_audit through assembly_preview",
        "SOUND: sfx_prompt_craft + mmaudio + mix",
        "SHIP: master_flow1",
    ]
    for p in phases:
        log.info(p)
    log.step("DRY-RUN", "Complete")


def run_driver(args: argparse.Namespace) -> int:
    config = load_config(_DRIVER_DIR / "config.yaml")
    if args.headed:
        config["headed"] = True
    if args.verbose:
        config["verbose"] = True

    session_dir = Path(args.session_dir) if args.session_dir else _CAMPAIGN_DIR / "logs" / f"session_{int(time.time())}"
    session_dir.mkdir(parents=True, exist_ok=True)
    log = EventLogger(session_dir)
    state_path = default_state_path(_CAMPAIGN_DIR)
    state = DriverState.load(state_path) if args.resume else DriverState()
    state.session_dir = str(session_dir)

    archive: ExecutionScreenshotArchive | None = None
    if not args.dry_run:
        archive = ExecutionScreenshotArchive(
            _REPO_ROOT,
            session_dir.name,
            archive_dir=config.get("execution_screenshots_dir", "ASSETS/flow1-gui-e2e-screenshots"),
            min_interval_s=float(config.get("execution_screenshot_min_interval_s", 120)),
            log=log,
        )
        log.info(f"Screenshot archive: {archive.archive_root} (max 1 per {archive.min_interval_s:.0f}s on click)")

    if args.dry_run:
        dry_run_journey(log)
        return EXIT_OK

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.fatal("playwright not installed — pip install -e 'CURSOR_EXECUTE/.[e2e]' && playwright install chromium")

    input_wav = _REPO_ROOT / config["input_wav"]
    dummy_vo = _CAMPAIGN_DIR / "fixtures" / "dummy_vo.wav"
    wav_name = input_wav.name
    api = ApiClient(
        config["base_url"],
        request_timeout_s=int(config.get("api_request_timeout_s", 30)),
    )

    poll_s = float(config.get("poll_interval_s", 2))
    heartbeat_s = float(config.get("heartbeat_interval_s", 30))
    stall_s = float(config.get("stall_timeout_s", 120))
    api_poll_max_failures = int(config.get("api_poll_max_consecutive_failures", 3))

    last_signature: tuple | None = None
    last_progress_at = time.time()
    last_heartbeat_at = 0.0
    last_stage_index: int | None = None
    consecutive_api_failures = 0
    last_api_error = ""
    run_id: str | None = state.run_id

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not config.get("headed"))
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            try:
                if not state.started or not state.run_id:
                    try:
                        baseline = start_run(page, log, config, wav_name, archive, api=api)
                    except TimeoutError as exc:
                        shot = screenshot(page, session_dir, "session-not-ready")
                        write_blocker(
                            _CAMPAIGN_DIR,
                            slug="session-not-ready",
                            run_id=None,
                            stage=None,
                            job_status=None,
                            symptom=str(exc),
                            screenshot=shot,
                            log_tail=[],
                        )
                        return EXIT_BLOCKER
                    state.started = True
                    run_id = resolve_run_id_after_start(
                        api, wav_name, page, log, baseline_run_ids=baseline
                    )
                    if not run_id:
                        shot = screenshot(page, session_dir, "no-run-id")
                        write_blocker(
                            _CAMPAIGN_DIR,
                            slug="no-run-id",
                            run_id=None,
                            stage=None,
                            job_status=None,
                            symptom="Could not capture run_id after Start",
                            screenshot=shot,
                            log_tail=[],
                        )
                        return EXIT_BLOCKER
                    state.run_id = run_id
                    log.info(f"Captured run_id={run_id}")
                    if not wait_for_gui_run_loaded(api, page, run_id, log):
                        shot = screenshot(page, session_dir, "run-not-loaded")
                        write_blocker(
                            _CAMPAIGN_DIR,
                            slug="run-not-loaded",
                            run_id=run_id,
                            stage=None,
                            job_status=None,
                            symptom="Execution created but GUI never opened it in LiveStatusBar",
                            screenshot=shot,
                            log_tail=[],
                        )
                        return EXIT_BLOCKER
                    state.save(state_path)
                else:
                    run_id = state.run_id
                    log.info(f"Resuming run_id={run_id}")
                    page.goto(f"{config['base_url']}/", wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

                while True:
                    if master_path(_REPO_ROOT, run_id).is_file():
                        log.step("DRIVER", f"Success: master.wav exists for {run_id}")
                        state.master_verified = True
                        state.save(state_path)
                        return EXIT_OK

                    try:
                        job = api.job(run_id)
                        status = job.get("status", "idle")
                        if status in ("running", "idle"):
                            run = {
                                "stages": [],
                                "g1_missing": [],
                                "selected_flow": job.get("selected_flow"),
                            }
                        elif status == "awaiting_write_approval":
                            run = {
                                "stages": [],
                                "g1_missing": [],
                                "selected_flow": job.get("selected_flow"),
                            }
                        else:
                            run = api.run(run_id)
                        consecutive_api_failures = 0
                        last_api_error = ""
                    except Exception as exc:
                        consecutive_api_failures += 1
                        last_api_error = str(exc)
                        remaining = api_poll_max_failures - consecutive_api_failures
                        if remaining > 0:
                            log.wait(
                                f"API poll failed ({exc}) — retrying "
                                f"({consecutive_api_failures}/{api_poll_max_failures})"
                            )
                            page.wait_for_timeout(int(poll_s * 1000))
                            continue
                        shot = screenshot(page, session_dir, "api-poll-failed")
                        path = write_blocker(
                            _CAMPAIGN_DIR,
                            slug="api-poll-failed",
                            run_id=run_id,
                            stage=None,
                            job_status="api_unreachable",
                            symptom=(
                                f"GET /api/runs/{run_id} or /job failed "
                                f"{consecutive_api_failures} times in a row: {last_api_error}"
                            ),
                            screenshot=shot,
                            log_tail=[],
                        )
                        log.blocker(f"Wrote {path}")
                        state.save(state_path)
                        return EXIT_BLOCKER
                    status = job.get("status", "idle")
                    stage = job.get("current_stage") or job.get("stage")
                    idx = job.get("stage_index")
                    total = job.get("stage_total")
                    log_tail = api.log_tail(run_id, 5)
                    last_msg = log_tail[-1].get("message", "") if log_tail else ""

                    signature = (status, stage, job.get("awaiting_write_approval"), job.get("needs_stage_reuse"))
                    now = time.time()

                    if idx != last_stage_index:
                        last_progress_at = now
                        last_stage_index = idx

                    if status == "running":
                        if config.get("verbose") or now - last_heartbeat_at >= heartbeat_s:
                            pct = f"{idx}/{total}" if idx is not None and total else "?"
                            elapsed = int(now - last_progress_at)
                            log.wait(
                                f"job=running stage={stage} ({pct}) elapsed={elapsed}s | last_log: {last_msg[:80]}"
                            )
                            last_heartbeat_at = now
                        page.wait_for_timeout(int(poll_s * 1000))
                        continue

                    if signature == last_signature and now - last_progress_at > stall_s:
                        shot = screenshot(page, session_dir, "stuck")
                        path = write_blocker(
                            _CAMPAIGN_DIR,
                            slug="stuck-state",
                            run_id=run_id,
                            stage=stage,
                            job_status=status,
                            symptom=f"Unchanged state {signature} for >{stall_s}s",
                            screenshot=shot,
                            log_tail=api.log_tail(run_id, 20),
                        )
                        log.blocker(f"Wrote {path}")
                        state.save(state_path)
                        return EXIT_BLOCKER

                    event = resolve_gates(page, log, job, run, dummy_vo, archive)
                    if event == "blocker:llm_gate":
                        shot = screenshot(page, session_dir, "llm-gate")
                        err = job.get("last_error") or {}
                        path = write_blocker(
                            _CAMPAIGN_DIR,
                            slug="llm-gate",
                            run_id=run_id,
                            stage=err.get("stage") or stage,
                            job_status="gate",
                            symptom=str(err.get("message") or "LLM gate"),
                            screenshot=shot,
                            log_tail=api.log_tail(run_id, 20),
                        )
                        log.blocker(f"Wrote {path}")
                        state.save(state_path)
                        return EXIT_BLOCKER

                    if event:
                        state.last_gate_cleared = event
                        state.last_stage = stage
                        state.last_action = event
                        state.save(state_path)
                        last_signature = signature
                        if event not in ("wait:job_running", "wait:gui_run_loading"):
                            last_progress_at = now
                        page.wait_for_timeout(int(poll_s * 1000))
                    else:
                        if signature == last_signature:
                            if now - last_progress_at > stall_s:
                                shot = screenshot(page, session_dir, "no-handler")
                                path = write_blocker(
                                    _CAMPAIGN_DIR,
                                    slug="no-handler",
                                    run_id=run_id,
                                    stage=stage,
                                    job_status=status,
                                    symptom="No gate handler matched and no primary CTA",
                                    screenshot=shot,
                                    log_tail=api.log_tail(run_id, 20),
                                )
                                log.blocker(f"Wrote {path}")
                                state.save(state_path)
                                return EXIT_BLOCKER
                        else:
                            last_progress_at = now
                        last_signature = signature
                        page.wait_for_timeout(int(poll_s * 1000))

            finally:
                browser.close()
    finally:
        if archive and archive.capture_count > 0:
            archive.commit_session(run_id, note="flow1-gui-e2e driver")

    return EXIT_OK


def main() -> None:
    parser = argparse.ArgumentParser(description="Flow 1 GUI E2E driver")
    parser.add_argument("--session-dir", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run_driver(args))


if __name__ == "__main__":
    main()
