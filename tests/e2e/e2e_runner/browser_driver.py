"""Playwright browser driver for GUI actions."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright


class BrowserDriver:
    def __init__(self, base_url: str, *, headless: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None
        self.page: Page | None = None

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context()
        self.page = self._ctx.new_page()
        self.page.goto(self.base_url)

    def stop(self) -> None:
        if self._ctx:
            self._ctx.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self.page = None

    def screenshot(self, path: str) -> None:
        if self.page:
            self.page.screenshot(path=path, full_page=True)

    def click_testid(self, test_id: str, *, timeout_ms: int = 5000) -> bool:
        if not self.page:
            return False
        try:
            self.page.get_by_test_id(test_id).click(timeout=timeout_ms)
            return True
        except Exception:
            return False

    def sync_active_session(self) -> bool:
        """Reload GUI after API run creation — avoids manual asset picker clicks."""
        if not self.page:
            return False
        try:
            self.page.goto(self.base_url)
            self.page.wait_for_load_state("networkidle", timeout=15000)
            return True
        except Exception:
            return False

    def start_execution(
        self,
        asset_basename: str,
        flow_intent: str,
    ) -> bool:
        if self.sync_active_session():
            return True
        if not self.page:
            return False
        try:
            self.page.get_by_test_id(f"flow-intent-{flow_intent}").click(timeout=3000)
        except Exception:
            pass
        asset_id = f"start-asset-{asset_basename}"
        if self.click_testid(asset_id):
            return self.click_testid("new-execution")
        try:
            self.page.get_by_role("button", name="New execution").first.click(timeout=5000)
            return True
        except Exception:
            return False

    def click_journey_cta(self) -> bool:
        if self.click_testid("journey-run-cta"):
            return True
        if not self.page:
            return False
        try:
            self.page.locator(".journey-run-cta").first.click(timeout=5000)
            return True
        except Exception:
            return False

    def open_checkpoint(self) -> bool:
        if self.click_testid("open-checkpoint"):
            return True
        if not self.page:
            return False
        try:
            self.page.get_by_role("button", name="Open checkpoint").click(timeout=3000)
            return True
        except Exception:
            return False

    def checkpoint_continue(self) -> bool:
        if self.click_testid("checkpoint-continue"):
            return True
        if not self.page:
            return False
        try:
            self.page.get_by_role("button", name="Continue to next step").click(timeout=3000)
            return True
        except Exception:
            return False

    def complete_transcript_review(self) -> bool:
        if self.click_testid("complete-transcript-review"):
            return True
        if not self.page:
            return False
        try:
            self.page.get_by_role("button", name="Accept remaining & complete").click(
                timeout=3000
            )
            return True
        except Exception:
            try:
                self.page.get_by_role("button", name="Complete transcript review").click(
                    timeout=3000
                )
                return True
            except Exception:
                return False

    def select_flow(self, flow: str) -> bool:
        if self.click_testid(f"select-flow-{flow}"):
            return True
        labels = {
            "flow1": "Flow 1 — Full podcast",
            "flow2": "Flow 2 — Highlight reel",
            "flow3": "Flow 3 — Show description",
        }
        if not self.page:
            return False
        try:
            self.page.get_by_role("button", name=labels.get(flow, flow)).click(timeout=5000)
            return True
        except Exception:
            return False

    def mark_profile_verified(self) -> bool:
        if self.click_testid("mark-profile-verified"):
            return True
        if not self.page:
            return False
        try:
            self.page.get_by_role("button", name="Mark verified").click(timeout=5000)
            return True
        except Exception:
            return False

    def grant_api_consent(self) -> bool:
        if not self.page:
            return False
        try:
            self.page.get_by_role("button", name="Allow all").click(timeout=3000)
            return True
        except Exception:
            try:
                self.page.get_by_role("button", name="Grant").first.click(timeout=3000)
                return True
            except Exception:
                return False
