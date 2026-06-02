import { useApp } from "../context/AppContext";
import { StatusHeader } from "./StatusHeader";
import { OperatorCommandBar } from "./OperatorCommandBar";
import { AppTabs } from "./AppTabs";
import { LogStrip } from "./LogStrip";
import { StartTab } from "./tabs/StartTab";
import { ExecutionsTab } from "./tabs/ExecutionsTab";
import { PipelineTab } from "./tabs/PipelineTab";
import { LogsTab } from "./tabs/LogsTab";
import { ModalHost } from "./modals/ModalHost";

export function AppShell() {
  const { activeTab } = useApp();

  return (
    <div className="operator-app">
      <StatusHeader />
      <OperatorCommandBar />
      <AppTabs />
      <div className="operator-body app-tab-content">
        {activeTab === "start" ? <StartTab /> : null}
        {activeTab === "executions" ? <ExecutionsTab /> : null}
        {activeTab === "pipeline" ? <PipelineTab /> : null}
        {activeTab === "logs" ? <LogsTab /> : null}
      </div>
      <LogStrip />
      <ModalHost />
    </div>
  );
}
