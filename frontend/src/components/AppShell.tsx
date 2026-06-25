import { useEffect } from "react";
import { useApp } from "../context/AppContext";
import { GlobalActivityDock } from "./activity/GlobalActivityDock";
import { AppTabs } from "./AppTabs";
import { ActivityTeaser } from "./activity/ActivityTeaser";
import { StartTab } from "./tabs/StartTab";
import { ExecutionsTab } from "./tabs/ExecutionsTab";
import { PipelineTab } from "./tabs/PipelineTab";
import { LogsTab } from "./tabs/LogsTab";
import { ModalHost } from "./modals/ModalHost";
import { Toast } from "./Toast";
import { ActionOverlay } from "./ActionOverlay";
import { LiveStatusBar } from "./LiveStatusBar";

export function AppShell() {
  const {
    activeTab,
    runId,
    dumpLastStep,
    traceAction,
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
    <div className={`operator-app${runId ? " operator-app-with-dock" : ""}`}>
      <LiveStatusBar />
      <AppTabs />
      <div className="operator-main-row">
        <div className="operator-body app-tab-content">
          {activeTab === "start" ? <StartTab /> : null}
          {activeTab === "executions" ? <ExecutionsTab /> : null}
          {activeTab === "pipeline" ? <PipelineTab /> : null}
          {activeTab === "logs" ? <LogsTab /> : null}
        </div>
        {runId ? (
          <GlobalActivityDock onDump={() => void dumpLastStep()} />
        ) : null}
      </div>
      {activeTab !== "pipeline" ? <ActivityTeaser /> : null}
      <ModalHost />
      <Toast />
      <ActionOverlay />
    </div>
  );
}
