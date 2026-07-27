/**
 * Preview annotations — confusing/dull/redundant tags feed priors or G1.5 delta only (CFI-capped).
 * Lightweight advisory surface; does not mutate stages.
 */
export function RefinementPreviewAnnotations({
  annotations,
}: {
  annotations?: Array<{ line_id?: string; tag: string; note?: string }> | null;
}) {
  if (!annotations?.length) return null;
  return (
    <section className="refinement-preview-annotations panel-inset" aria-label="Preview annotations">
      <h4 className="refinement-subsection-title">Preview annotations</h4>
      <ul className="refinement-skip-list">
        {annotations.map((a, i) => (
          <li key={`${a.line_id || "x"}-${a.tag}-${i}`}>
            <strong>{a.tag}</strong>
            {a.line_id ? <> · {a.line_id}</> : null}
            {a.note ? <> — {a.note}</> : null}
          </li>
        ))}
      </ul>
      <p className="hint sm">Advisory only — may bias soft priors; re-runs stay CFI-capped.</p>
    </section>
  );
}
