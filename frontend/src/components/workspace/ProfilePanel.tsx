import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import {
  collectAnalysisProfileFromForm,
  loadProfileToForm,
  type ProfileFormState,
} from "./profileForm";
import type { AnalysisState } from "../../types";

const emptyForm: ProfileFormState = {
  title: "",
  summary: "",
  thesis: "",
  themes: "",
  questions: "",
  tone: "",
  pacing: "",
  intStyle: "",
  eeStyle: "",
  notes: "",
};

export function ProfilePanel() {
  const { run, selectedStage, refreshRun, showToast, confirm } = useApp();
  const [form, setForm] = useState<ProfileFormState>(emptyForm);
  const [baseState, setBaseState] = useState<AnalysisState | null>(null);
  const [verified, setVerified] = useState(false);
  const [status, setStatus] = useState("");

  const show =
    selectedStage?.id === "analysis_profile" ||
    run?.stages?.find((s) => s.id === "analysis_profile")?.status !== "locked";

  const loadProfile = useCallback(async () => {
    if (!run) return;
    try {
      const data = await api<{
        analysis_state: AnalysisState;
        operator_verified?: boolean;
        completion?: { blockers?: string[] };
      }>(`/api/runs/${run.run_id}/analysis-profile`);
      setBaseState(data.analysis_state);
      setForm(loadProfileToForm(data.analysis_state));
      setVerified(Boolean(data.operator_verified));
      setStatus(
        data.completion?.blockers?.length
          ? `Blockers: ${data.completion.blockers.join("; ")}`
          : "Loaded profile",
      );
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Load failed");
    }
  }, [run]);

  useEffect(() => {
    if (show && selectedStage?.id === "analysis_profile") void loadProfile();
  }, [show, selectedStage?.id, loadProfile]);

  if (!show) return null;

  const saveProfile = async () => {
    if (!run) return;
    const data = collectAnalysisProfileFromForm(form, baseState);
    const invalidate = (await confirm(
      "Save profile? Re-run downstream AI stages if needed.",
    ))
      ? "content_context"
      : null;
    try {
      await api(`/api/runs/${run.run_id}/analysis-profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data, invalidate_from: invalidate }),
      });
      showToast("Profile saved");
      await refreshRun();
      await loadProfile();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Save failed");
    }
  };

  const verifyProfile = async () => {
    if (!run) return;
    const data = collectAnalysisProfileFromForm(form, baseState);
    await api(`/api/runs/${run.run_id}/analysis-profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data, operator_verified: true }),
    });
    await api(`/api/runs/${run.run_id}/analysis-profile/verify`, {
      method: "POST",
    });
    showToast("Profile verified");
    await refreshRun();
    await loadProfile();
  };

  const setField = (key: keyof ProfileFormState, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="panel profile-panel">
      <div className="panel-head">
        <h3>Interview profile</h3>
        {verified ? <span className="profile-badge">Verified</span> : null}
      </div>
      <p className="hint">
        Per-interview themes, major questions, and style. Saved to{" "}
        <code>understanding/analysis_state.json</code>. Edit here or in the file
        editor below.
      </p>
      <div className="profile-grid">
        <label className="profile-field">
          <span>Episode title</span>
          <input
            type="text"
            value={form.title}
            onChange={(e) => setField("title", e.target.value)}
            placeholder="Optional title"
          />
        </label>
        <label className="profile-field full">
          <span>One-line summary</span>
          <input
            type="text"
            value={form.summary}
            onChange={(e) => setField("summary", e.target.value)}
            placeholder="What this interview is about"
          />
        </label>
        <label className="profile-field full">
          <span>Thesis</span>
          <textarea
            rows={2}
            value={form.thesis}
            onChange={(e) => setField("thesis", e.target.value)}
            placeholder="Main takeaway"
          />
        </label>
        <label className="profile-field full">
          <span>
            Major themes (one per line: <code>id | label | summary</code>)
          </span>
          <textarea
            rows={6}
            spellCheck={false}
            value={form.themes}
            onChange={(e) => setField("themes", e.target.value)}
          />
        </label>
        <label className="profile-field full">
          <span>Major questions (one per line)</span>
          <textarea
            rows={4}
            spellCheck={false}
            value={form.questions}
            onChange={(e) => setField("questions", e.target.value)}
          />
        </label>
        <label className="profile-field">
          <span>Tone</span>
          <input
            type="text"
            value={form.tone}
            onChange={(e) => setField("tone", e.target.value)}
          />
        </label>
        <label className="profile-field">
          <span>Pacing</span>
          <input
            type="text"
            value={form.pacing}
            onChange={(e) => setField("pacing", e.target.value)}
          />
        </label>
        <label className="profile-field">
          <span>Interviewer style</span>
          <input
            type="text"
            value={form.intStyle}
            onChange={(e) => setField("intStyle", e.target.value)}
          />
        </label>
        <label className="profile-field">
          <span>Interviewee style</span>
          <input
            type="text"
            value={form.eeStyle}
            onChange={(e) => setField("eeStyle", e.target.value)}
          />
        </label>
        <label className="profile-field full">
          <span>Operator notes</span>
          <textarea
            rows={2}
            value={form.notes}
            onChange={(e) => setField("notes", e.target.value)}
          />
        </label>
      </div>
      <div className="profile-actions">
        <button type="button" className="btn primary sm" onClick={() => void saveProfile()}>
          Save profile
        </button>
        <button type="button" className="btn ghost sm" data-testid="mark-profile-verified" onClick={() => void verifyProfile()}>
          Mark verified
        </button>
        <button type="button" className="btn ghost sm" onClick={() => void loadProfile()}>
          Reload
        </button>
      </div>
      <p className="save-status">{status}</p>
    </div>
  );
}
