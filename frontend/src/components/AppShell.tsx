import { useApp } from "../context/AppContext";
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
import { LiveStatusBar } from "./LiveStatusBar";

export function AppShell() {
  const { activeTab, run, pendingActionCount } = useApp();

  return (
    <div className="operator-app">
      <LiveStatusBar />
      {run && pendingActionCount > 0 && activeTab !== "pipeline" ? (
        <div className="global-pending-action-wrap">
          <PendingActionBanner compact />
          <AttentionQueuePanel compact />
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
      <Toast />
    </div>
  );
}
