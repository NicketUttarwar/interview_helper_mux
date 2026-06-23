import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { validateArtifactWrite } from "../../schemas/validateArtifact";
import { useApp } from "../../context/AppContext";
import {
  collectAnalysisProfileFromForm,
  loadProfileToForm,
  type ProfileFormState,
} from "./profileForm";
import {
  FORMAT_CLASS_VALUES,
  TONE_CLASS_VALUES,
  formatClassLabel,
} from "../../utils/toneTaxonomy";
import { formatApiError } from "../../utils/safeApi";
import type { AnalysisState } from "../../types";
import { ActionMarker } from "../guidance/ActionMarker";

const emptyForm: ProfileFormState = {
  title: "",
  summary: "",
  thesis: "",
  themes: "",
  questions: "",
  tone: "",
  toneClass: "",
  formatClass: "",
  formatNotes: "",
  pacing: "",
  intStyle: "",
  eeStyle: "",
  notes: "",
};

export function ProfilePanel() {
  const { run, selectedStage, refreshRun, showToast, appendClientLog, confirm, runNextStage } = useApp();
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
      const msg = formatApiError(e, "Load profile");
      setStatus(msg);
      showToast(msg, "error");
      appendClientLog(msg, "error", "analysis_profile");
    }
  }, [run, showToast, appendClientLog]);

  useEffect(() => {
    if (show && run?.profile_ready_for_review) void loadProfile();
  }, [show, run?.profile_ready_for_review, loadProfile]);

  if (!show) {
    return (
      <div className="panel profile-panel">
        <h3>Interview profile</h3>
        <p className="hint">
          The profile editor unlocks when the analysis profile stage is available in the pipeline.
        </p>
      </div>
    );
  }

  if (!run?.profile_ready_for_review && !run?.profile_verified) {
    const profileStage = run?.stages?.find((s) => s.id === "analysis_profile");
    const items = profileStage?.guidance
      ? [...(profileStage.guidance.prerequisites || []), ...(profileStage.guidance.actions || [])]
      : [
          {
            id: "wait",
            label: "Complete transcript review and understanding analysis first",
            status: "todo" as const,
          },
        ];
    return (
      <div className="panel profile-panel">
        <h3>Interview profile</h3>
        <ul className="stage-guidance-list">
          {items.map((item) => (
            <li key={item.id} className={`stage-guidance-item status-${item.status}`}>
              <ActionMarker status={item.status} />
              <span className="stage-guidance-label">{item.label}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const saveProfile = async () => {
    if (!run) return;
    const data = collectAnalysisProfileFromForm(form, baseState);
    const v = validateArtifactWrite("understanding/analysis_state.json", data);
    if (!v.ok) {
      showToast(`Profile schema errors: ${v.errors[0]}`, "error");
      return;
    }
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
      const msg = formatApiError(e, "Save profile");
      showToast(msg, "error");
      appendClientLog(msg, "error", "analysis_profile");
    }
  };

  const verifyProfile = async () => {
    if (!run) return;
    const data = collectAnalysisProfileFromForm(form, baseState);
    try {
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
      await runNextStage();
    } catch (e) {
      const msg = formatApiError(e, "Verify profile");
      showToast(msg, "error");
      appendClientLog(msg, "error", "analysis_profile");
    }
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
        AI-generated themes, major questions, and style. Saved to{" "}
        <code>understanding/analysis_state.json</code>. Review here, edit if needed,
        then mark verified.
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
          <span>Tone class</span>
          <select
            value={form.toneClass}
            onChange={(e) => setField("toneClass", e.target.value)}
          >
            <option value="">— Select —</option>
            {TONE_CLASS_VALUES.map((v) => (
              <option key={v} value={v}>
                {formatClassLabel(v)}
              </option>
            ))}
          </select>
        </label>
        <label className="profile-field">
          <span>Tone (nuance)</span>
          <input
            type="text"
            value={form.tone}
            onChange={(e) => setField("tone", e.target.value)}
            placeholder="e.g. warm investigative, not sensational"
          />
        </label>
        <label className="profile-field">
          <span>Format</span>
          <select
            value={form.formatClass}
            onChange={(e) => setField("formatClass", e.target.value)}
          >
            <option value="">— Select —</option>
            {FORMAT_CLASS_VALUES.map((v) => (
              <option key={v} value={v}>
                {formatClassLabel(v)}
              </option>
            ))}
          </select>
        </label>
        <label className="profile-field">
          <span>Pacing</span>
          <input
            type="text"
            value={form.pacing}
            onChange={(e) => setField("pacing", e.target.value)}
          />
        </label>
        <label className="profile-field full">
          <span>Format notes</span>
          <input
            type="text"
            value={form.formatNotes}
            onChange={(e) => setField("formatNotes", e.target.value)}
            placeholder="Panel guests, media format, etc."
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
