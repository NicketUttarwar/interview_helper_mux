import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { useApp } from "../../context/AppContext";
import { ArtifactAudio } from "../shared/ArtifactAudio";

export interface GPublishReviewState {
  title: string;
  description: string;
  word_count?: number;
  cover?: {
    path?: string | null;
    source?: string;
    candidates?: Array<{ path: string; label: string; selected?: boolean }>;
  };
  master?: {
    relative_path?: string | null;
    absolute_path?: string | null;
    publish_relative?: string | null;
    publish_absolute?: string | null;
  };
  audio_mp3?: {
    relative_path?: string | null;
    absolute_path?: string | null;
  };
  package_ready?: boolean;
  run_dir?: string;
  editable?: boolean;
}

interface Props {
  enabled: boolean;
  onSaved?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

function mediaUrl(runId: string, rel: string): string {
  return `/api/runs/${runId}/audio?path=${encodeURIComponent(rel)}`;
}

export function GPublishReviewSection({ enabled, onSaved, onDirtyChange }: Props) {
  const { runId, showToast, appendClientLog } = useApp();
  const [review, setReview] = useState<GPublishReviewState | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedCover, setSelectedCover] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const dirtyRef = useRef(false);

  const markDirty = (dirty: boolean) => {
    dirtyRef.current = dirty;
    onDirtyChange?.(dirty);
  };

  const reload = useCallback(async () => {
    if (!runId || !enabled) return;
    setLoading(true);
    try {
      const data = await api<GPublishReviewState>(`/api/runs/${runId}/g-publish/review`);
      setReview(data);
      if (!dirtyRef.current) {
        setTitle(data.title || "");
        setDescription(data.description || "");
        const current =
          data.cover?.candidates?.find((c) => c.selected)?.path || data.cover?.path || null;
        setSelectedCover(current);
      }
    } catch {
      setReview(null);
    } finally {
      setLoading(false);
    }
  }, [runId, enabled]);

  useEffect(() => {
    dirtyRef.current = false;
    void reload();
  }, [reload, runId]);

  if (!enabled || !runId) return null;

  const masterRel = review?.master?.relative_path || "master/master.wav";
  const masterAbs = review?.master?.absolute_path || null;
  const coverPath = review?.cover?.path || null;
  const candidates = review?.cover?.candidates || [];
  const wordCount = description.trim() ? description.trim().split(/\s+/).length : 0;

  const save = async () => {
    if (!runId) return;
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      showToast("Episode title is required.", "warning");
      return;
    }
    setSaving(true);
    try {
      const body: { title: string; description: string; cover_path?: string } = {
        title: trimmedTitle,
        description: description.trim() || trimmedTitle,
      };
      const currentCover =
        review?.cover?.candidates?.find((c) => c.selected)?.path || review?.cover?.path;
      if (selectedCover && selectedCover !== currentCover) {
        body.cover_path = selectedCover;
      }
      const updated = await api<GPublishReviewState>(`/api/runs/${runId}/g-publish/review`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setReview(updated);
      setTitle(updated.title || "");
      setDescription(updated.description || "");
      const nextCover =
        updated.cover?.candidates?.find((c) => c.selected)?.path || updated.cover?.path || null;
      setSelectedCover(nextCover);
      dirtyRef.current = false;
      onDirtyChange?.(false);
      appendClientLog("G-Publish review saved", "action", "podcast_publish", "gui.g_publish.review");
      showToast("Publish package updated", "success");
      onSaved?.();
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setSaving(false);
    }
  };

  const uploadCover = async (file: File) => {
    if (!runId) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/runs/${runId}/g-publish/cover`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Upload failed (${res.status})`);
      }
      dirtyRef.current = false;
      await reload();
      appendClientLog("G-Publish cover uploaded", "action", "podcast_publish", "gui.g_publish.cover");
      showToast("Cover image updated", "success");
      onSaved?.();
    } catch (err) {
      showToast(String(err), "error");
    } finally {
      setUploading(false);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  };

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      showToast("Path copied", "success");
    } catch {
      showToast("Could not copy path", "warning");
    }
  };

  return (
    <section className="g-publish-review" data-testid="g-publish-review">
      <div className="g-publish-review-head">
        <h3>Review before upload</h3>
        <p className="hint">
          Edit the episode title, show description, and cover art. Listen to the final master, then
          save your changes before uploading to S3.
        </p>
      </div>

      {loading && !review ? (
        <p className="hint gate-loading">
          <span className="spinner-inline" aria-hidden /> Loading publish package…
        </p>
      ) : null}

      {review ? (
        <div className="g-publish-review-body">
          <label className="g-publish-field">
            <span className="g-publish-field-label">Episode title</span>
            <input
              type="text"
              className="g-publish-input"
              data-testid="g-publish-title"
              value={title}
              onChange={(e) => {
                markDirty(true);
                setTitle(e.target.value);
              }}
              disabled={saving || uploading}
            />
          </label>

          <label className="g-publish-field">
            <span className="g-publish-field-label">
              Show description
              <span className="g-publish-word-count">{wordCount} words</span>
            </span>
            <textarea
              className="g-publish-textarea artifact-editor"
              data-testid="g-publish-description"
              rows={8}
              value={description}
              onChange={(e) => {
                markDirty(true);
                setDescription(e.target.value);
              }}
              disabled={saving || uploading}
            />
          </label>

          <div className="g-publish-field">
            <span className="g-publish-field-label">Cover art</span>
            {coverPath ? (
              <div className="g-publish-cover-current">
                <img
                  src={mediaUrl(runId, coverPath)}
                  alt="Current episode cover"
                  className="g-publish-cover-preview"
                />
                <p className="hint sm">Source: {review.cover?.source || "unknown"}</p>
              </div>
            ) : (
              <p className="hint">Cover not ready yet — prepare the package first.</p>
            )}
            {candidates.length > 1 ? (
              <div className="g-publish-cover-grid" role="listbox" aria-label="Cover candidates">
                {candidates.map((candidate) => (
                  <button
                    key={candidate.path}
                    type="button"
                    role="option"
                    aria-selected={selectedCover === candidate.path}
                    className={`g-publish-cover-option${
                      selectedCover === candidate.path ? " selected" : ""
                    }`}
                    onClick={() => {
                      markDirty(true);
                      setSelectedCover(candidate.path);
                    }}
                    disabled={saving || uploading}
                  >
                    <img src={mediaUrl(runId, candidate.path)} alt={candidate.label} />
                    <span>{candidate.label}</span>
                  </button>
                ))}
              </div>
            ) : null}
            <div className="g-publish-cover-upload">
              <input
                ref={uploadRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="sr-only"
                data-testid="g-publish-cover-upload"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void uploadCover(file);
                }}
              />
              <button
                type="button"
                className="btn sm ghost"
                disabled={saving || uploading}
                onClick={() => uploadRef.current?.click()}
              >
                {uploading ? "Uploading…" : "Upload custom cover"}
              </button>
            </div>
          </div>

          {masterAbs ? (
            <div className="g-publish-field">
              <span className="g-publish-field-label">Final master</span>
              <div className="g-publish-master-row">
                <code className="g-publish-master-path" data-testid="g-publish-master-path">
                  {masterAbs}
                </code>
                <button
                  type="button"
                  className="btn sm ghost"
                  onClick={() => void copyPath(masterAbs)}
                >
                  Copy path
                </button>
              </div>
              {masterRel ? (
                <div className="g-publish-master-audio">
                  <ArtifactAudio
                    src={mediaUrl(runId, masterRel)}
                    className="pipeline-complete-audio"
                    data-testid="g-publish-master-audio"
                  />
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="g-publish-review-actions">
            <button
              type="button"
              className="btn primary"
              data-testid="g-publish-save-review"
              disabled={saving || uploading}
              onClick={() => void save()}
            >
              {saving ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
