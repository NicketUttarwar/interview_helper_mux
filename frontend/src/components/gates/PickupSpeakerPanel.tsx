import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import type { StageInfo } from "../../types";
import { formatApiError } from "../../utils/safeApi";
import { traceAction } from "../../operator/traceAction";
import { ArtifactAudio } from "../shared/ArtifactAudio";

interface PickupSpeakerRow {
  speaker_id: string;
  role_hint?: string;
  talk_ms?: number;
  talk_minutes?: number;
  talk_ratio?: number;
  is_least_spoken?: boolean;
  sample_clip_path?: string | null;
}

interface PickupSpeakerPayload {
  speakers: PickupSpeakerRow[];
  least_spoken_speaker_id?: string;
  pickup_eligible_speaker_id?: string;
  pickup_speaker_confirmed?: boolean;
  gap_fill_skipped?: boolean;
  pending?: boolean;
}

function formatRole(role?: string): string {
  if (!role || role === "unknown") return "Speaker";
  return role.replace(/_/g, " ");
}

export function PickupSpeakerPanel({ stage }: { stage: StageInfo }) {
  const { runId, run, refreshRun, showToast, advanceFromCheckpoint, closeActionModal } = useApp();
  const [data, setData] = useState<PickupSpeakerPayload | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    try {
      const res = await api<PickupSpeakerPayload>(`/api/runs/${runId}/pickup-speaker`);
      setData(res);
      setSelected(res.pickup_eligible_speaker_id || res.least_spoken_speaker_id || "");
    } catch (e) {
      showToast(formatApiError(e, "Load pickup speakers"), "error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [runId, showToast]);

  useEffect(() => {
    void load();
  }, [load, run?.flow_adaptation?.pickup_eligible_speaker_id, run?.pickup_speaker_pending]);

  const selectSpeaker = async (speakerId: string) => {
    if (!runId || busy || speakerId === selected) {
      setSelected(speakerId);
      return;
    }
    setSelected(speakerId);
    try {
      await api(`/api/runs/${runId}/pickup-speaker`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pickup_eligible_speaker_id: speakerId }),
      });
    } catch (e) {
      showToast(formatApiError(e, "Select speaker"), "error");
      await load();
    }
  };

  const confirm = async () => {
    if (!runId || !selected || busy) return;
    setBusy(true);
    traceAction("gui.adaptation.pickup_speaker", "Confirming gap pickup speaker", {
      stage: stage.id,
      meta: { speaker_id: selected },
    });
    try {
      await api(`/api/runs/${runId}/pickup-speaker/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pickup_eligible_speaker_id: selected }),
      });
      showToast("Gap pickup speaker confirmed — gap evaluation can continue.");
      await load();
      await refreshRun();
      closeActionModal();
      await advanceFromCheckpoint();
    } catch (e) {
      showToast(formatApiError(e, "Confirm pickup speaker"), "error");
    } finally {
      setBusy(false);
    }
  };

  const skipGapFill = async () => {
    if (!runId || busy) return;
    setBusy(true);
    traceAction("gui.gap_fill.skip", "Skipping gap speaker sections", { stage: stage.id });
    try {
      await api(`/api/runs/${runId}/gap-fill/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      showToast(
        "Gap speaker sections skipped — continuing with source audio only (no new VO).",
        "success",
      );
      await load();
      await refreshRun();
      closeActionModal();
      await advanceFromCheckpoint();
    } catch (e) {
      showToast(formatApiError(e, "Skip gap speaker sections"), "error");
    } finally {
      setBusy(false);
    }
  };

  if (loading && !data) {
    return (
      <p className="hint gate-loading">
        <span className="spinner-inline" aria-hidden /> Loading speakers…
      </p>
    );
  }

  if (data?.gap_fill_skipped || run?.gap_fill_mode === "skipped") {
    return (
      <section className="pickup-speaker-panel panel-inset" data-testid="pickup-speaker-panel">
        <h4>Gap speaker sections skipped</h4>
        <p className="hint sm">
          This run will not add gap-fill VO or new interviewer lines. The pipeline will reposition
          and polish existing source segments only.
        </p>
      </section>
    );
  }

  if (!data?.speakers?.length) {
    return (
      <p className="hint">
        Speaker stats are not ready yet. Complete source topology analysis first.
      </p>
    );
  }

  const confirmed = Boolean(data.pickup_speaker_confirmed);
  const defaultId = data.least_spoken_speaker_id || "";

  return (
    <section className="pickup-speaker-panel panel-inset" data-testid="pickup-speaker-panel">
      <h4>Gap pickup speaker</h4>
      <p className="hint sm">
        Choose who will record new gap-fill lines during realtime pickup. By default this is the
        speaker with the least talk time in the source audio
        {defaultId ? (
          <>
            {" "}
            (<strong>{defaultId}</strong>)
          </>
        ) : null}
        . Listen to a sample from each speaker, then confirm your choice before gap questions are
        generated.
      </p>
      <p className="hint sm">
        <strong>No new VO needed?</strong> Skip gap speaker sections to use the source as-is — no
        gap analysis, no pickup recordings, no new speech. The edit will reposition segments and
        add SFX/polish only.
      </p>

      <ul className="pickup-speaker-list">
        {data.speakers.map((sp) => {
          const checked = selected === sp.speaker_id;
          const clipUrl =
            runId && sp.sample_clip_path
              ? `/api/runs/${runId}/audio?path=${encodeURIComponent(sp.sample_clip_path)}`
              : null;
          return (
            <li
              key={sp.speaker_id}
              className={`pickup-speaker-card vo-card${checked ? " selected" : ""}`}
            >
              <label className="pickup-speaker-select">
                <input
                  type="radio"
                  name="pickup-speaker"
                  checked={checked}
                  disabled={busy || confirmed}
                  onChange={() => void selectSpeaker(sp.speaker_id)}
                />
                <span className="pickup-speaker-label">
                  <strong>{sp.speaker_id}</strong>
                  <span className="muted sm">
                    {formatRole(sp.role_hint)}
                    {sp.is_least_spoken ? " · default (least speech)" : ""}
                  </span>
                </span>
              </label>
              <p className="muted sm pickup-speaker-stats">
                {typeof sp.talk_minutes === "number" ? `${sp.talk_minutes} min` : "—"} talk
                {typeof sp.talk_ratio === "number"
                  ? ` · ${Math.round(sp.talk_ratio * 100)}% of audio`
                  : ""}
              </p>
              {clipUrl ? (
                <ArtifactAudio
                  preload="none"
                  src={clipUrl}
                  onError={() =>
                    showToast(
                      "Could not load speaker sample — check that source topology ran successfully.",
                      "error",
                    )
                  }
                />
              ) : (
                <p className="hint sm">No sample clip available for this speaker.</p>
              )}
            </li>
          );
        })}
      </ul>

      {confirmed ? (
        <p className="hint sm">✓ Gap pickup speaker confirmed ({data.pickup_eligible_speaker_id})</p>
      ) : (
        <div className="pickup-speaker-actions">
          <button
            type="button"
            className="btn primary sm"
            data-testid="confirm-pickup-speaker"
            data-action-id="gui.adaptation.pickup_speaker"
            disabled={busy || !selected}
            onClick={() => void confirm()}
          >
            {busy ? (
              <>
                <span className="spinner-inline" aria-hidden /> Confirming…
              </>
            ) : (
              "Confirm gap pickup speaker"
            )}
          </button>
          <button
            type="button"
            className="btn ghost sm"
            data-testid="skip-gap-fill"
            data-action-id="gui.gap_fill.skip"
            disabled={busy}
            onClick={() => void skipGapFill()}
          >
            Skip gap speaker sections
          </button>
        </div>
      )}
    </section>
  );
}
