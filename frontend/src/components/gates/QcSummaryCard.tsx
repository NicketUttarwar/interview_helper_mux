import { useApp } from "../../context/AppContext";

export function QcSummaryCard({ qcKey }: { qcKey: string }) {
  const { run, setActiveTab } = useApp();
  const summary = run?.meta?.qc_summaries?.[qcKey];
  if (!summary) return null;

  const labels: Record<string, string> = {
    narrative_qc: "Flow 1 narrative QC",
    edl_narrative_qc: "Flow 1 EDL narrative QC",
    show_description_qc: "Show description QC",
  };
  const label = labels[qcKey] || qcKey;

  return (
    <div className={`qc-summary-card ${summary.passed ? "qc-pass" : "qc-fail"}`}>
      <h4>{label}</h4>
      <p>
        {summary.passed ? "Pass" : "Fail"}
        {summary.strict ? " (strict)" : ""}
      </p>
      {Array.isArray(summary.errors) && summary.errors.length ? (
        <ul>
          {summary.errors.slice(0, 4).map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      ) : null}
      {!summary.passed ? (
        <p className="hint">
          Fix issues in the Logs tab, edit artifacts in Files if needed, then use{" "}
          <strong>Redo from selected stage</strong> in the sidebar and re-run this step.
        </p>
      ) : null}
      {!summary.passed ? (
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => setActiveTab("logs")}
        >
          View Logs
        </button>
      ) : null}
    </div>
  );
}
