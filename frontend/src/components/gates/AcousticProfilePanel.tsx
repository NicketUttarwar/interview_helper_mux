import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import {
  PACE_CLASS_OPTIONS,
  SAP_PATH,
  UNDERSCORE_POLICY_OPTIONS,
  escapeHtml,
} from "../../utils";

export function AcousticProfilePanel() {
  const { run, refreshRun, showToast, confirm } = useApp();
  const [paceOverride, setPaceOverride] = useState("");
  const [policyOverride, setPolicyOverride] = useState("");
  const [derivedPace, setDerivedPace] = useState("—");
  const [derivedPolicy, setDerivedPolicy] = useState("—");
  const [status, setStatus] = useState("");
  const [loaded, setLoaded] = useState(false);

  const loadProfile = useCallback(async () => {
    if (!run) return;
    try {
      const profile = await api<Record<string, unknown>>(
        `/api/runs/${run.run_id}/artifact?path=${encodeURIComponent(SAP_PATH)}`,
      );
      setDerivedPace(
        String((profile?.pacing as Record<string, unknown>)?.pace_class || "—"),
      );
      setDerivedPolicy(
        String(
          (profile?.mix_contract as Record<string, unknown>)?.underscore_policy ||
            "—",
        ),
      );
      const overrides = profile?.operator_overrides as Record<string, unknown> | undefined;
      setPaceOverride(
        String((overrides?.pacing as Record<string, unknown>)?.pace_class || ""),
      );
      setPolicyOverride(
        String(
          (overrides?.mix_contract as Record<string, unknown>)?.underscore_policy ||
            "",
        ),
      );
      setLoaded(true);
    } catch {
      setLoaded(false);
    }
  }, [run]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const recompute = async () => {
    if (!run) return;
    if (!(await confirm("Recompute acoustic profile from current ingest/transcript?")))
      return;
    await api(`/api/runs/${run.run_id}/recompute-acoustic-profile`, {
      method: "POST",
    });
    showToast("Acoustic profile recomputed.");
    await refreshRun();
    await loadProfile();
  };

  const saveOverrides = async (overrides: Record<string, string>) => {
    if (!run) return;
    const res = await api<{ effective?: Record<string, string> }>(
      `/api/runs/${run.run_id}/acoustic-profile/overrides`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ overrides }),
      },
    );
    const eff = res?.effective || {};
    setStatus(
      `Saved — effective pace=${eff.pace_class || "—"} underscore=${eff.underscore_policy || "—"}`,
    );
    showToast("Acoustic overrides saved");
    await refreshRun();
    await loadProfile();
  };

  return (
    <>
      <button type="button" className="btn sm primary" onClick={() => void recompute()}>
        Recompute profile
      </button>
      <div className="quality-offer-card acoustic-overrides-card">
        <h4>Operator overrides</h4>
        <p className="muted">
          Tune pace and underscore policy without re-running DSP. Leave blank to use
          derived values.
        </p>
        {!loaded ? (
          <p className="hint">
            Run <strong>Source acoustic profile</strong> first.
          </p>
        ) : (
          <div className="acoustic-overrides-form">
            <label className="tr-label">
              pace_class <span className="muted">(derived: {escapeHtml(derivedPace)})</span>
              <select
                className="select"
                value={paceOverride}
                onChange={(e) => setPaceOverride(e.target.value)}
              >
                {PACE_CLASS_OPTIONS.map((v) => (
                  <option key={v} value={v}>
                    {v || "— use derived —"}
                  </option>
                ))}
              </select>
            </label>
            <label className="tr-label">
              underscore_policy{" "}
              <span className="muted">(derived: {escapeHtml(derivedPolicy)})</span>
              <select
                className="select"
                value={policyOverride}
                onChange={(e) => setPolicyOverride(e.target.value)}
              >
                {UNDERSCORE_POLICY_OPTIONS.map((v) => (
                  <option key={v} value={v}>
                    {v || "— use derived —"}
                  </option>
                ))}
              </select>
            </label>
            <div className="flow-choice">
              <button
                type="button"
                className="btn primary sm"
                onClick={() => {
                  const overrides: Record<string, string> = {};
                  if (paceOverride) overrides.pace_class = paceOverride;
                  if (policyOverride) overrides.underscore_policy = policyOverride;
                  void saveOverrides(overrides).catch((e) =>
                    setStatus(e instanceof Error ? e.message : "Save failed"),
                  );
                }}
              >
                Save overrides
              </button>
              <button
                type="button"
                className="btn sm"
                onClick={async () => {
                  if (
                    !(await confirm(
                      "Clear all operator overrides and use derived values?",
                    ))
                  )
                    return;
                  await saveOverrides({});
                  setPaceOverride("");
                  setPolicyOverride("");
                }}
              >
                Clear overrides
              </button>
            </div>
            <p className="save-status">{status}</p>
          </div>
        )}
      </div>
    </>
  );
}
