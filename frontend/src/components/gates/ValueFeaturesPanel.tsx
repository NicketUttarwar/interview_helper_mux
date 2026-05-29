import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import {
  VALUE_FEATURES_PATH,
  formatValueMetric,
  formatValueTags,
} from "../../utils";

export function ValueFeaturesPanel() {
  const { run } = useApp();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!run) return;
    void api<Record<string, unknown>>(
      `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent(VALUE_FEATURES_PATH)}`,
    )
      .then(setData)
      .catch(() => {
        setData(null);
        setMissing(true);
      });
  }, [run]);

  const profiles = (data?.profiles || {}) as Record<string, Record<string, unknown>>;
  const rows: Array<[string, unknown]> = [];
  const tr = profiles.transcript;
  if (tr) {
    rows.push(
      ["Transcript · WPM proxy", tr.words_per_minute_proxy],
      ["Transcript · median pause (ms)", tr.median_pause_ms],
      ["Transcript · segments", tr.segment_count],
      [
        "Transcript · segment p50 / p90",
        `${formatValueMetric(tr.segment_length_p50)} / ${formatValueMetric(tr.segment_length_p90)}`,
      ],
      ["Transcript · interviewer turn ratio", tr.interviewer_turn_ratio],
      [
        "Transcript · tags",
        formatValueTags(tr.tags as Record<string, string[]>).join(", ") || "—",
      ],
    );
  }
  const au = profiles.audio;
  if (au) {
    rows.push(
      ["Audio · duration (s)", au.duration_sec],
      ["Audio · silence ratio", au.silence_ratio],
      [
        "Audio · RMS p50 / p90",
        `${formatValueMetric(au.rms_p50)} / ${formatValueMetric(au.rms_p90)}`,
      ],
      ["Audio · peak dBFS proxy", au.peak_dbfs_proxy],
    );
  }

  return (
    <div className="quality-offer-card value-features-card">
      <h4>Value features</h4>
      <p className="muted">Deterministic metrics when value_analysis is enabled.</p>
      {missing ? (
        <>
          <p className="hint">
            No <code>{VALUE_FEATURES_PATH}</code> yet. With{" "}
            <code>value_analysis.enabled</code> in config, run:
          </p>
          <p className="hint">
            <code>
              python tools/extract_value_features.py --run-id {run?.run_id} --profile
              all
            </code>
          </p>
        </>
      ) : !rows.length ? (
        <p className="hint">
          <code>{VALUE_FEATURES_PATH}</code> exists but has no profiles — re-run the
          extractor.
        </p>
      ) : (
        <>
          <dl className="value-features-dl">
            {rows.map(([label, value]) => (
              <div key={label} style={{ display: "contents" }}>
                <dt>{label}</dt>
                <dd>{formatValueMetric(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="muted">
            run_id {String(data?.run_id || run?.run_id)} · {VALUE_FEATURES_PATH}
          </p>
        </>
      )}
    </div>
  );
}
