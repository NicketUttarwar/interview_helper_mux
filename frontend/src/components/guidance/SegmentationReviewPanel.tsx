import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { StageInfo } from "../../types";

interface SegmentationReviewReport {
  source_paths?: Record<string, { path?: string; staged?: boolean }>;
  contract?: {
    segment_count?: number;
    timeline_valid?: boolean;
    segment_ids?: string[];
    timeline_errors?: string[];
  };
  parity_errors?: string[];
  cross_validate_errors?: string[];
  pending_paths?: string[];
  ready?: boolean;
}

interface SegmentRow {
  segment_id?: string;
  start_ms?: number;
  end_ms?: number;
  speaker_id?: string;
  type?: string;
  speaker_role?: string;
  topic_tags?: string[];
}

export function SegmentationReviewPanel({ stage }: { stage: StageInfo }) {
  const { runId, config } = useApp();
  const unified = config?.journey_ui?.segmentation_unified_review !== false;
  const [report, setReport] = useState<SegmentationReviewReport | null>(null);
  const [boundaries, setBoundaries] = useState<SegmentRow[]>([]);
  const [manifest, setManifest] = useState<SegmentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!runId || !unified || stage.id !== "segment_classification") {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const review = await api<SegmentationReviewReport>(`/api/runs/${runId}/segmentation-review`);
      setReport(review);
      const boundaryDoc = await api<{ boundaries?: SegmentRow[] }>(
        `/api/runs/${runId}/pending-writes/segment_classification/content?path=${encodeURIComponent("segments/boundaries.json")}`,
      );
      const manifestDoc = await api<{ segments?: SegmentRow[] }>(
        `/api/runs/${runId}/pending-writes/segment_classification/content?path=${encodeURIComponent("segments/manifest.json")}`,
      );
      setBoundaries(boundaryDoc.boundaries || []);
      setManifest(manifestDoc.segments || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load segmentation review");
    } finally {
      setLoading(false);
    }
  }, [runId, unified, stage.id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!unified || stage.id !== "segment_classification") return null;

  if (loading) {
    return <p className="hint"><span className="spinner-inline" aria-hidden /> Loading segmentation review…</p>;
  }

  if (error) {
    return (
      <div className="segmentation-review-error" role="alert">
        <p className="hint">{error}</p>
        <button type="button" className="btn ghost sm" onClick={() => void load()}>
          Retry
        </button>
      </div>
    );
  }

  const contract = report?.contract;
  const timelineOk = contract?.timeline_valid !== false;
  const crossOk = !(report?.cross_validate_errors || []).length;
  const parityOk = !(report?.parity_errors || []).length;

  return (
    <section className="segmentation-review-panel panel-inset" aria-label="Segmentation unified review">
      <h4 className="stage-outputs-title">Segmentation review</h4>
      <p className="hint sm">
        Boundaries and manifest are reviewed together before save. Timeline authority lives in{" "}
        <code>segments/boundaries.json</code>; manifest carries semantic fields only.
      </p>

      <div className="segmentation-review-badges">
        <span className={`badge ${timelineOk ? "ok" : "fail"}`}>
          Timeline {timelineOk ? "valid" : "invalid"}
        </span>
        <span className={`badge ${parityOk ? "ok" : "fail"}`}>Field parity {parityOk ? "ok" : "issues"}</span>
        <span className={`badge ${crossOk ? "ok" : "fail"}`}>Cross-artifact {crossOk ? "pass" : "fail"}</span>
        {contract?.segment_count != null ? (
          <span className="badge neutral">{contract.segment_count} segments</span>
        ) : null}
      </div>

      {report?.source_paths ? (
        <ul className="segmentation-review-sources hint sm">
          {Object.entries(report.source_paths).map(([key, meta]) => (
            <li key={key}>
              <strong>{key}</strong>: <code>{meta.path}</code>
              {meta.staged ? " (staged)" : " (committed)"}
            </li>
          ))}
        </ul>
      ) : null}

      {(report?.parity_errors || []).length ? (
        <div className="segmentation-review-errors" role="alert">
          <p className="hint"><strong>Parity</strong></p>
          <ul>
            {(report?.parity_errors || []).slice(0, 6).map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {(report?.cross_validate_errors || []).length ? (
        <div className="segmentation-review-errors" role="alert">
          <p className="hint"><strong>Cross-artifact</strong></p>
          <ul>
            {(report?.cross_validate_errors || []).slice(0, 6).map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="segmentation-review-tables">
        <div>
          <h5>Boundaries (read-only)</h5>
          <table className="segmentation-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Start</th>
                <th>End</th>
                <th>Speaker</th>
              </tr>
            </thead>
            <tbody>
              {boundaries.slice(0, 24).map((row) => (
                <tr key={row.segment_id}>
                  <td><code>{row.segment_id}</code></td>
                  <td>{row.start_ms}</td>
                  <td>{row.end_ms}</td>
                  <td>{row.speaker_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h5>Manifest classification</h5>
          <table className="segmentation-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Role</th>
                <th>Tags</th>
              </tr>
            </thead>
            <tbody>
              {manifest.slice(0, 24).map((row) => (
                <tr key={row.segment_id}>
                  <td><code>{row.segment_id}</code></td>
                  <td>{row.type}</td>
                  <td>{row.speaker_role}</td>
                  <td>{(row.topic_tags || []).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
