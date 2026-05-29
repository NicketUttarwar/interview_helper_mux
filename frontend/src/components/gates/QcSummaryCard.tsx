import { useApp } from "../../context/AppContext";

export function QcSummaryCard({ qcKey }: { qcKey: string }) {
  const { run } = useApp();
  const summary = run?.meta?.qc_summaries?.[qcKey];
  if (!summary) return null;

  const label =
    qcKey === "narrative_qc" ? "Flow 1 narrative QC" : "Show description QC";

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
    </div>
  );
}
