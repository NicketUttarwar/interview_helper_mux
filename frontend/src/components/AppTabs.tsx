import { useEffect, useMemo, useState } from "react";
import type { AppTab } from "../types";
import { useApp } from "../context/AppContext";

const TABS: { id: AppTab; label: string }[] = [
  { id: "start", label: "Start" },
  { id: "executions", label: "Executions" },
  { id: "pipeline", label: "Pipeline" },
  { id: "logs", label: "Logs" },
];

export function AppTabs() {
  const { activeTab, setActiveTab, pendingActionCount, logEntries, sessionReady } = useApp();
  const errorCount = useMemo(
    () => logEntries.filter((e) => e.level === "error").length,
    [logEntries],
  );
  const [ackedErrors, setAckedErrors] = useState(0);

  useEffect(() => {
    if (activeTab === "logs") setAckedErrors(errorCount);
  }, [activeTab, errorCount]);

  const unseenErrors = Math.max(0, errorCount - ackedErrors);

  return (
    <nav className="app-tabs" aria-label="Main navigation">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`app-tab${activeTab === tab.id ? " active" : ""}`}
          aria-current={activeTab === tab.id ? "page" : undefined}
          disabled={!sessionReady && tab.id !== "logs"}
          onClick={() => setActiveTab(tab.id)}
        >
          {tab.label}
          {tab.id === "pipeline" && pendingActionCount > 0 ? (
            <span className="app-tab-badge">{pendingActionCount}</span>
          ) : null}
          {tab.id === "logs" && unseenErrors > 0 ? (
            <span className="app-tab-badge app-tab-badge-error" title="Errors in log">
              {unseenErrors}
            </span>
          ) : null}
        </button>
      ))}
    </nav>
  );
}
