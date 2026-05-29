import type { AppTab } from "../types";
import { useApp } from "../context/AppContext";

const TABS: { id: AppTab; label: string }[] = [
  { id: "start", label: "Start" },
  { id: "executions", label: "Executions" },
  { id: "pipeline", label: "Pipeline" },
  { id: "logs", label: "Logs" },
];

export function AppTabs() {
  const { activeTab, setActiveTab, pendingActionCount } = useApp();

  return (
    <nav className="app-tabs" aria-label="Main navigation">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`app-tab${activeTab === tab.id ? " active" : ""}`}
          aria-current={activeTab === tab.id ? "page" : undefined}
          onClick={() => setActiveTab(tab.id)}
        >
          {tab.label}
          {tab.id === "pipeline" && pendingActionCount > 0 ? (
            <span className="app-tab-badge">{pendingActionCount}</span>
          ) : null}
        </button>
      ))}
    </nav>
  );
}
