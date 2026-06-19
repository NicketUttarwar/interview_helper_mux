"""Gate resolution handlers — dummy GUI clicks for Flow 1 E2E."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from execution_screenshots import ExecutionScreenshotArchive
    from logging_banner import EventLogger


def _click_testid(
    page: Page,
    testid: str,
    log: EventLogger,
    label: str,
    archive: ExecutionScreenshotArchive | None = None,
) -> bool:
    loc = page.get_by_test_id(testid)
    if loc.count() == 0:
        return False
    target = loc.first
    try:
        if not target.is_enabled():
            return False
    except Exception:
        return False
    log.action(f"Clicking data-testid={testid} ({label})")
    target.click(timeout=5000)
    if archive:
        archive.maybe_capture_after_click(page, f"click:{testid}")
    return True


def _click_role(
    page: Page,
    name: str,
    log: EventLogger,
    exact: bool = False,
    archive: ExecutionScreenshotArchive | None = None,
) -> bool:
    loc = page.get_by_role("button", name=name, exact=exact)
    if loc.count() == 0:
        return False
    target = loc.first
    try:
        if not target.is_enabled():
            return False
    except Exception:
        return False
    log.action(f"Clicking button '{name}'")
    target.click(timeout=5000)
    if archive:
        archive.maybe_capture_after_click(page, f"click:{name}")
    return True


def try_write_approval(page: Page, log: EventLogger, archive=None) -> bool:
    if _click_testid(page, "write-approval-save-continue", log, "write approval", archive):
        return True
    if page.locator("#write-approval-panel").count() and _click_role(
        page, "Save & continue", log, archive=archive
    ):
        return True
    return _click_role(page, "Save & continue", log, archive=archive)


def try_handoff(page: Page, log: EventLogger, archive=None) -> bool:
    if _click_testid(page, "handoff-acknowledge", log, "handoff", archive):
        return True
    if _click_role(page, "Acknowledge & continue", log, archive=archive):
        return True
    return _click_role(page, "Acknowledge and continue", log, archive=archive)


def try_reuse_decline(page: Page, log: EventLogger, archive=None) -> bool:
    if _click_testid(page, "reuse-run-fresh", log, "reuse decline", archive):
        return True
    return _click_role(page, "Run fresh instead", log, archive=archive)


def try_preclean_dismiss(page: Page, log: EventLogger, archive=None) -> bool:
    for checkpoint in ("before_ingest", "g1_vo_pickup"):
        tid = f"preclean-dismiss-{checkpoint}"
        if _click_testid(page, tid, log, f"preclean dismiss {checkpoint}", archive):
            return True
    return False


def try_g0_transcript(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("G0 transcript review")
    if _click_testid(page, "complete-transcript-review", log, "complete transcript review", archive):
        return True
    return _click_role(page, "Complete transcript review", log, archive=archive)


def try_g0_disfluency(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("G0.5 disfluency review")
    if _click_testid(page, "disfluency-confirm-all", log, "confirm all disfluencies", archive):
        pass
    else:
        while _click_role(page, "Confirm", log, archive=archive):
            page.wait_for_timeout(300)
    if _click_testid(page, "complete-disfluency-review", log, "complete disfluency", archive):
        return True
    return _click_role(page, "Complete review", log, archive=archive)


def try_profile(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("Profile verification")
    if _click_testid(page, "mark-profile-verified", log, "mark profile verified", archive):
        return True
    if _click_testid(page, "mark-profile-verified-modal", log, "mark profile verified modal", archive):
        return True
    return _click_role(page, "Mark profile verified", log, archive=archive)


def try_g1_vo(page: Page, log: EventLogger, dummy_vo: Path, archive=None) -> bool:
    log.gate("G1 VO pickup upload")
    uploads = page.locator("input.vo-upload[type='file']")
    count = uploads.count()
    if count == 0:
        return False
    for i in range(count):
        tid_attr = uploads.nth(i).get_attribute("data-testid")
        label = tid_attr or f"vo-upload-{i}"
        log.action(f"Uploading {dummy_vo.name} via {label}")
        uploads.nth(i).set_input_files(str(dummy_vo))
        page.wait_for_timeout(500)
    try_preclean_dismiss(page, log, archive)
    if _click_testid(page, "vo-continue", log, "vo continue", archive):
        return True
    return _click_role(page, "All VO recorded — continue", log, archive=archive)


def try_g2_flow(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("G2 flow select flow1")
    if _click_testid(page, "select-flow-flow1", log, "select flow1", archive):
        return True
    return _click_role(page, "flow1", log, archive=archive)


def try_g1_5_sfx(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("G1.5 SFX prompt approval")
    if _click_testid(page, "approve-sfx-prompts", log, "approve sfx prompts", archive):
        return True
    return _click_role(page, "Approve prompts", log, archive=archive)


def try_sfx_post_listen(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("SFX post-listen pass")
    if _click_testid(page, "sfx-post-listen-pass-all", log, "pass all sfx", archive):
        return True
    passed = False
    while _click_role(page, "Pass", log, archive=archive):
        passed = True
        page.wait_for_timeout(300)
    return passed


def try_preview_listen(page: Page, log: EventLogger, archive=None) -> bool:
    log.gate("Preview listen milestone")
    return _click_role(page, "I've listened to the preview", log, archive=archive) or _click_role(
        page, "Mark preview listened", log, archive=archive
    )


def try_modal_continue(page: Page, log: EventLogger, archive=None) -> bool:
    if _click_testid(page, "checkpoint-continue", log, "checkpoint continue", archive):
        return True
    return False


def try_primary_cta(page: Page, log: EventLogger, archive=None) -> bool:
    """Prefer StepActionHeader primary, then modal checkpoint, then sidebar substeps."""
    for tid in (
        "step-action-primary",
        "checkpoint-continue",
        "write-approval-save-continue",
        "live-status-primary",
    ):
        if _click_testid(page, tid, log, "primary CTA", archive):
            return True
    loc = page.locator(
        "button.pipeline-substep-row.status-todo, button.pipeline-substep-row.status-running"
    )
    if loc.count() > 0:
        tid = loc.first.get_attribute("data-testid")
        if tid and _click_testid(page, tid, log, "sidebar substep", archive):
            return True
    return False


def try_active_substep(
    page: Page,
    log: EventLogger,
    run: dict[str, Any],
    archive: ExecutionScreenshotArchive | None = None,
) -> bool:
    """Click the journey-active substep in the Steps sidebar when visible."""
    journey = run.get("journey") or {}
    sub_id = journey.get("active_substep_id")
    if sub_id and _click_testid(page, f"substep-{sub_id}", log, f"active substep {sub_id}", archive):
        return True
    loc = page.locator(
        "button.pipeline-substep-row.status-todo, button.pipeline-substep-row.status-running"
    )
    if loc.count() == 0:
        return False
    tid = loc.first.get_attribute("data-testid")
    if not tid:
        return False
    return _click_testid(page, tid, log, "first actionable substep", archive)


def click_substep(
    page: Page,
    log: EventLogger,
    run: dict[str, Any] | None = None,
    *,
    substep_id: str | None = None,
    archive: ExecutionScreenshotArchive | None = None,
) -> bool:
    """Click a sidebar substep by id or fall back to journey-active / first todo substep."""
    if substep_id and _click_testid(page, f"substep-{substep_id}", log, f"substep {substep_id}", archive):
        return True
    if run and try_active_substep(page, log, run, archive):
        return True
    return False


def resolve_gates(
    page: Page,
    log: EventLogger,
    job: dict[str, Any],
    run: dict[str, Any],
    dummy_vo: Path,
    archive=None,
) -> str | None:
    """Try gate handlers in priority order. Returns event name if handled."""

    if job.get("awaiting_write_approval") or job.get("status") == "awaiting_write_approval":
        if try_write_approval(page, log, archive):
            return "gate:write_approval"

    if page.locator("#stage-handoff-panel, .handoff-panel").count():
        if try_handoff(page, log, archive):
            return "gate:handoff"

    if job.get("needs_stage_reuse") or page.locator(".stage-reuse-offer").count():
        if try_reuse_decline(page, log, archive):
            return "gate:reuse_decline"

    if try_preclean_dismiss(page, log, archive):
        return "gate:preclean_dismiss"

    if not page_has_active_run(page):
        if try_modal_continue(page, log, archive):
            return "gate:modal_continue"
        if try_primary_cta(page, log, archive):
            return "action:primary_cta"
        return "wait:gui_run_loading"

    stages = {s.get("id"): s for s in run.get("stages") or [] if isinstance(s, dict)}
    action_stages = [sid for sid, s in stages.items() if s.get("status") == "action_required"]

    if "transcript_review" in action_stages or page.get_by_test_id("complete-transcript-review").count():
        if try_g0_transcript(page, log, archive):
            return "gate:g0"

    if "disfluency_review" in action_stages:
        if try_g0_disfluency(page, log, archive):
            return "gate:g0_5"

    if "analysis_profile" in action_stages:
        if try_profile(page, log, archive):
            return "gate:profile"

    g1_missing = run.get("g1_missing") or []
    if g1_missing or "g1_vo_pickup" in action_stages:
        if try_g1_vo(page, log, dummy_vo, archive):
            return "gate:g1_upload"

    if not g1_missing and "g1_vo_pickup" in action_stages:
        if try_g1_vo(page, log, dummy_vo, archive):
            return "gate:g1_continue"

    if "g2_flow_select" in action_stages or not run.get("selected_flow"):
        if try_g2_flow(page, log, archive):
            return "gate:g2"

    if "sfx_prompt_craft" in action_stages or page.get_by_role("button", name="Approve prompts").count():
        if try_g1_5_sfx(page, log, archive):
            return "gate:g1_5"

    if try_sfx_post_listen(page, log, archive):
        return "gate:sfx_post_listen"

    if try_preview_listen(page, log, archive):
        return "gate:preview_listen"

    if job.get("status") == "gate":
        return "blocker:llm_gate"

    if job.get("status") == "running":
        return "wait:job_running"

    if try_modal_continue(page, log, archive):
        return "gate:modal_continue"

    if try_active_substep(page, log, run, archive):
        return "action:substep"

    if try_primary_cta(page, log, archive):
        return "action:primary_cta"

    return None


def page_has_active_run(page: Page) -> bool:
    """True when LiveStatusBar shows an opened execution (not the empty Start state)."""
    bar = page.get_by_test_id("live-status-bar")
    if bar.count() == 0:
        return False
    try:
        text = bar.first.inner_text()
    except Exception:
        return False
    return "No active run" not in text and "Pick source audio on Start" not in text


def baseline_run_ids_for_wav(rows: list[dict[str, Any]], wav_name: str) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        path = str(row.get("input_audio_path") or "")
        if wav_name not in path:
            continue
        rid = row.get("run_id")
        if rid:
            ids.add(str(rid))
    return ids


def newest_run_after_baseline(
    rows: list[dict[str, Any]], wav_name: str, baseline: set[str]
) -> str | None:
    """Return the newest execution for this WAV that was not in baseline."""
    fresh = [r for r in rows if str(r.get("run_id") or "") not in baseline]
    return newest_matching_run(fresh, wav_name)


def newest_matching_run(rows: list[dict[str, Any]], wav_name: str) -> str | None:
    """Return run_id of the newest execution for this source file name."""
    matches: list[dict[str, Any]] = []
    for row in rows:
        path = str(row.get("input_audio_path") or "")
        if wav_name not in path:
            continue
        rid = row.get("run_id")
        if rid:
            matches.append(row)
    if not matches:
        return None
    best = max(
        matches,
        key=lambda r: (
            int(r.get("execution_number") or 0),
            str(r.get("created_at") or ""),
            str(r.get("run_id") or ""),
        ),
    )
    return str(best.get("run_id"))


def wait_for_start_tab_ready(
    page: Page,
    exec_testid: str,
    timeout_s: int = 120,
    log: "EventLogger | None" = None,
) -> None:
    """Wait until React boot finished (start-tab-ready marker or enabled Start button)."""
    deadline = time.time() + timeout_s
    marker = page.locator('[data-testid="start-tab-ready"][data-ready="true"]')
    btn = page.get_by_test_id(exec_testid).first
    while time.time() < deadline:
        try:
            if marker.count() > 0:
                if log:
                    log.info("Start tab ready (start-tab-ready marker)")
                return
        except Exception:
            pass
        try:
            if btn.is_enabled():
                if log:
                    log.info("Start tab ready (execution button enabled)")
                return
        except Exception:
            pass
        page.wait_for_timeout(500)
    raise TimeoutError(
        f"Start tab never became ready within {timeout_s}s "
        f"(expected start-tab-ready[data-ready=true] or enabled {exec_testid})"
    )


def resolve_run_id_after_start(
    api,
    wav_name: str,
    page: Page,
    log: EventLogger,
    *,
    baseline_run_ids: set[str] | None = None,
) -> str | None:
    """Prefer a newly created run (session active or runs list) after Start click."""
    baseline = baseline_run_ids or set()
    for attempt in range(90):
        try:
            active = (api.session().get("active") or {}).get("run_id")
            if active and (not baseline or str(active) not in baseline):
                api.run(str(active))
                log.info(f"run_id from session active (attempt {attempt + 1})")
                return str(active)
        except Exception:
            pass
        try:
            rows = list(api.runs().get("runs") or [])
            rid = newest_run_after_baseline(rows, wav_name, baseline) if baseline else newest_matching_run(
                rows, wav_name
            )
            if rid:
                log.info(f"run_id from runs list (attempt {attempt + 1})")
                return rid
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return extract_run_id_from_page(page)


def wait_for_gui_run_loaded(api, page: Page, run_id: str, log: EventLogger, timeout_s: int = 90) -> bool:
    """Wait until session + LiveStatusBar reflect the opened execution."""
    for attempt in range(timeout_s):
        session_ok = False
        try:
            active = (api.session().get("active") or {}).get("run_id")
            session_ok = str(active or "") == run_id
        except Exception:
            pass
        if session_ok and page_has_active_run(page):
            log.info(f"GUI loaded run_id={run_id} (attempt {attempt + 1})")
            return True
        page.wait_for_timeout(1000)
    return False


def extract_run_id_from_page(page: Page) -> str | None:
    text = page.content()
    m = re.search(r"exec_\d+_[a-f0-9]{12}_[0-9TZ]+", text)
    return m.group(0) if m else None
