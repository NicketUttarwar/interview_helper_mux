import { Suspense, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { GlobalActivityDock } from "./activity/GlobalActivityDock";
import { AppTabs } from "./AppTabs";
import { ActivityTeaser } from "./activity/ActivityTeaser";
import {
  LazyExecutionsTab,
  LazyLogsTab,
  LazyPipelineTab,
  LazyStartTab,
} from "./tabs/lazyTabs";
import { ModalHost } from "./modals/ModalHost";
import { SessionStaleOverlay } from "./SessionStaleOverlay";
import { Toast } from "./Toast";
import { ActionOverlay } from "./ActionOverlay";
import { LiveStatusBar } from "./LiveStatusBar";

function TabLoadingFallback() {
  return (
    <div className="tab-loading gate-loading" role="status" aria-live="polite">
      <span className="spinner-inline" aria-hidden="true" />
      Loading…
    </div>
  );
}

export function AppShell() {
  const {
    activeTab,
    runId,
    dumpLastStep,
    traceAction,
    activityLogCollapsed,
  } = useApp();

  useEffect(() => {
    const onClick = (ev: MouseEvent) => {
      const target = ev.target as HTMLElement | null;
      const el = target?.closest<HTMLElement>("[data-action-id]");
      if (!el) return;
      const actionId = el.getAttribute("data-action-id");
      if (!actionId) return;
      const label = el.getAttribute("aria-label") || el.textContent?.trim() || actionId;
      traceAction(actionId, label, { level: "action" });
    };
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [traceAction]);

  return (
    <div
      className={`operator-app${runId ? " operator-app-with-dock" : ""}${activityLogCollapsed ? " operator-dock-collapsed" : ""}`}
    >
      <LiveStatusBar />
      <AppTabs />
      <div className="operator-main-row">
        <div className="operator-body app-tab-content">
          <Suspense fallback={<TabLoadingFallback />}>
            {activeTab === "start" ? <LazyStartTab /> : null}
            {activeTab === "executions" ? <LazyExecutionsTab /> : null}
            {activeTab === "pipeline" ? <LazyPipelineTab /> : null}
            {activeTab === "logs" ? <LazyLogsTab /> : null}
          </Suspense>
        </div>
        {runId ? (
          <GlobalActivityDock onDump={() => void dumpLastStep()} />
        ) : null}
      </div>
      {activeTab !== "pipeline" ? <ActivityTeaser /> : null}
      <ModalHost />
      <SessionStaleOverlay />
      <Toast />
      <ActionOverlay />
    </div>
  );
}
