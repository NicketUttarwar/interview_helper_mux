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
  const { run, refreshRun, showToast, confirm, selectStage } = useApp();
  const [paceOverride, setPaceOverride] = useState("");
  const [policyOverride, setPolicyOverride] = useState("");
  const [derivedPace, setDerivedPace] = useState("—");
  const [derivedPolicy, setDerivedPolicy] = useState("—");
  const [status, setStatus] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [invalidateHint, setInvalidateHint] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

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
    if (!run || recomputing) return;
    if (!(await confirm("Recompute acoustic profile from current ingest/transcript?")))
      return;
    setRecomputing(true);
    showToast("Recomputing acoustic profile…");
    try {
      await api(`/api/runs/${run.run_id}/recompute-acoustic-profile`, {
        method: "POST",
      });
      showToast("Acoustic profile recomputed.");
      await refreshRun();
      await loadProfile();
    } finally {
      setRecomputing(false);
    }
  };

  const saveOverrides = async (overrides: Record<string, string>) => {
    if (!run) return;
    const hasOverrides = Object.keys(overrides).length > 0;
    const body: { overrides: Record<string, string>; invalidate_from?: string } = {
      overrides,
    };
    if (hasOverrides) body.invalidate_from = "sound_design_palettes";

    const res = await api<{ effective?: Record<string, string> }>(
      `/api/runs/${run.run_id}/acoustic-profile/overrides`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const eff = res?.effective || {};
    setStatus(
      `Saved — effective pace=${eff.pace_class || "—"} underscore=${eff.underscore_policy || "—"}`,
    );
    if (hasOverrides) {
      showToast(
        "Overrides saved — downstream sound design invalidated. Re-run from Sound design palettes.",
      );
      setInvalidateHint(true);
    } else {
      showToast("Acoustic overrides cleared");
    }
    await refreshRun();
    await loadProfile();
  };

  return (
    <>
      <button
        type="button"
        className="btn sm primary"
        disabled={recomputing}
        onClick={() => void recompute()}
      >
        {recomputing ? (
          <>
            <span className="spinner-inline" aria-hidden /> Recomputing…
          </>
        ) : (
          "Recompute profile"
        )}
      </button>
      <div className="quality-offer-card acoustic-overrides-card">
        <h4>Operator overrides</h4>
        <p className="muted">
          Tune pace and underscore policy without re-running DSP. Leave blank to use
          derived values. Underscore overrides also rebuild soundscape policy when present.
        </p>
        {invalidateHint ? (
          <p className="hint sm">
            Pace or policy overrides invalidate palettes and downstream sound design. Re-run
            from <strong>Sound design palettes</strong>.
          </p>
        ) : null}
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
              {invalidateHint ? (
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => void selectStage("sound_design_palettes")}
                >
                  Open sound design palettes
                </button>
              ) : null}
            </div>
            <p className="save-status">{status}</p>
          </div>
        )}
      </div>
    </>
  );
}
