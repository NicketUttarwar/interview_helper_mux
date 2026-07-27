import type { RefinementChampionEntry, RefinementRecomposeAccept } from "../../types";
import { refinementClassLabel, refinementReasonLabel } from "../../utils/refinementLabels";

interface Props {
  champion?: Record<string, RefinementChampionEntry>;
  /** Last gap_framing_recompose accept/reject verdict — the one case with a real candidate to compare. */
  lastRecomposeAccept?: RefinementRecomposeAccept;
}

function formatScore(v: number): string {
  return Number.isFinite(v) ? v.toFixed(2) : "—";
}

/**
 * Current champion per refinement domain, plus (when available) the most recent
 * gap_framing_recompose candidate's scores next to the champion it was judged against —
 * the one refinement pass that persists a real challenger to compare, not just the winner.
 */
export function RefinementChampionPanel({ champion, lastRecomposeAccept }: Props) {
  const domains = Object.keys(champion || {}).sort();
  if (!domains.length) return null;

  const compareKeys = lastRecomposeAccept
    ? Array.from(
        new Set([
          ...Object.keys(lastRecomposeAccept.champion_scores || {}),
          ...Object.keys(lastRecomposeAccept.candidate_scores || {}),
        ]),
      ).sort()
    : [];

  const allKernelKeys = Array.from(
    new Set(domains.flatMap((d) => Object.keys(champion![d].score_vector || {}))),
  ).sort();

  return (
    <div className="refinement-champion-panel" data-testid="refinement-champion-panel">
      <h5 className="refinement-subsection-title">Current champion by domain</h5>
      <ul className="refinement-champion-list">
        {domains.map((domain) => {
          const entry = champion![domain];
          return (
            <li key={domain} className="refinement-champion-row">
              <span className="refinement-champion-domain">{refinementClassLabel(domain)}</span>
              <span className="hint sm refinement-champion-source">
                source: {entry.source || "draft"}
              </span>
              <span className="refinement-champion-scores">
                {Object.entries(entry.score_vector || {}).map(([k, v]) => (
                  <span key={k} className="refinement-kernel-chip">
                    {k}: {formatScore(v)}
                  </span>
                ))}
              </span>
            </li>
          );
        })}
      </ul>

      {compareKeys.length ? (
        <div className="refinement-candidate-compare" data-testid="refinement-candidate-compare">
          <h5 className="refinement-subsection-title">Champion vs. last candidate (host VO)</h5>
          <p className="hint sm">
            {lastRecomposeAccept!.accepted
              ? "Candidate beat the champion and was promoted."
              : `Candidate kept the champion — ${refinementReasonLabel(lastRecomposeAccept!.reason_code)}.`}
          </p>
          <table className="refinement-kernel-table">
            <thead>
              <tr>
                <th>Kernel</th>
                <th>Champion</th>
                <th>Candidate</th>
              </tr>
            </thead>
            <tbody>
              {compareKeys.map((k) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>
                    {lastRecomposeAccept!.champion_scores?.[k] !== undefined
                      ? formatScore(lastRecomposeAccept!.champion_scores[k])
                      : "—"}
                  </td>
                  <td>
                    {lastRecomposeAccept!.candidate_scores?.[k] !== undefined
                      ? formatScore(lastRecomposeAccept!.candidate_scores[k])
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {allKernelKeys.length ? (
        <details className="refinement-kernel-details">
          <summary className="muted sm">Kernel scores dashboard (advanced)</summary>
          <table className="refinement-kernel-table">
            <thead>
              <tr>
                <th>Domain</th>
                {allKernelKeys.map((k) => (
                  <th key={k}>{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {domains.map((domain) => {
                const entry = champion![domain];
                return (
                  <tr key={domain}>
                    <td>{refinementClassLabel(domain)}</td>
                    {allKernelKeys.map((k) => (
                      <td key={k}>
                        {entry.score_vector?.[k] !== undefined
                          ? formatScore(entry.score_vector[k])
                          : "—"}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      ) : null}
    </div>
  );
}
