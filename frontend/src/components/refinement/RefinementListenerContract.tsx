import { useApp } from "../../context/AppContext";
import { useRefinementSummary } from "../../hooks/useRefinementSummary";

/** Ship-phase advisory checklist from champion + cascade readiness. */
export function RefinementListenerContract() {
  const { run, runId, openArtifactInEditor } = useApp();
  const summary = useRefinementSummary(runId, run);
  if (!run) return null;

  const hasChampion = Boolean(summary.champion?.gap_vo);
  const cascade = summary.cascade;
  const items = [
    {
      id: "gap_authoritative",
      ok: Boolean(run.stages?.some((s) => s.id === "gap_framing_recompose" && s.status === "done")),
      label: "Gap report authoritative (recompose or skip-copy)",
    },
    {
      id: "champion",
      ok: hasChampion,
      label: "Champion host VO recorded",
    },
    {
      id: "cascade",
      ok: cascade != null,
      label: cascade
        ? `Cascade noted (${(cascade.line_ids_changed || []).length} changed lines)`
        : "Cascade plan (after promote)",
    },
    {
      id: "g1_reachable",
      ok: true,
      label: "G1 reachable for draft or final lines",
    },
  ];

  return (
    <section className="refinement-listener-contract panel-inset" aria-label="Listener contract">
      <h4 className="refinement-subsection-title">Listener contract (advisory)</h4>
      <ul className="refinement-contract-list">
        {items.map((item) => (
          <li key={item.id} data-ok={item.ok ? "1" : "0"}>
            <span aria-hidden="true">{item.ok ? "✓" : "○"}</span> {item.label}
          </li>
        ))}
      </ul>
      {hasChampion ? (
        <button
          type="button"
          className="btn-link sm"
          onClick={() => openArtifactInEditor("understanding/refinement_champion/gap_vo.json")}
        >
          Open champion artifact
        </button>
      ) : null}
    </section>
  );
}
