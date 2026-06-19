import { useApp } from "../context/AppContext";
import { useGlobalOperatorAction } from "../hooks/useOperatorAction";
import { PendingActionBanner } from "./guidance/PendingActionBanner";
import { AttentionQueuePanel } from "./guidance/AttentionQueuePanel";
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
    run,
    pendingActionCount,
    selectedStageId,
    jobRunning,
    apiGrants,
  } = useApp();

  const operatorAction = useGlobalOperatorAction(run, {
    selectedStageId,
    jobRunning,
    apiGrants,
  });

  const showPendingWrap =
    run &&
    pendingActionCount > 0 &&
    activeTab !== "pipeline" &&
    !(operatorAction.mode === "needs_you" && pendingActionCount === 1);

  const showAttentionQueue =
    pendingActionCount > 1 &&
    !(operatorAction.mode === "needs_you" && operatorAction.stageId);

  return (
    <div className="operator-app">
      <LiveStatusBar />
      {showPendingWrap ? (
        <div className="global-pending-action-wrap">
          <PendingActionBanner compact />
          {showAttentionQueue ? <AttentionQueuePanel compact /> : null}
        </div>
      ) : null}
      <AppTabs />
      <div className="operator-body app-tab-content">
        {activeTab === "start" ? <StartTab /> : null}
        {activeTab === "executions" ? <ExecutionsTab /> : null}
        {activeTab === "pipeline" ? <PipelineTab /> : null}
        {activeTab === "logs" ? <LogsTab /> : null}
      </div>
      <ActivityTeaser />
      <ModalHost />
      <ActionOverlay />
      <Toast />
    </div>
  );
}
