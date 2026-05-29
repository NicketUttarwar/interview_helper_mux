/** Interview Helper Mux — web GUI with NLE, persistent log, session restore */

const state = {
  runId: null,
  run: null,
  selectedStageId: null,
  selectedSegmentId: null,
  selectedAsset: null,
  timeline: null,
  nle: null,
  jobPoll: null,
  logPoll: null,
  config: null,
  logCount: 0,
  playheadMs: 0,
  zoom: 1,
  transcriptReview: null,
  transcriptReviewIndex: 0,
  shownPrecleanOffers: new Set(),
  apiConsent: { providers: [], grants: {} },
  pendingExecute: null,
  lastNotifiedTs: null,
  lastActionRequiredId: null,
  jobStatusPrev: null,
  artifactIsJson: true,
};

const API_CONSENT_PREFIX = "api_consent_";

const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : err.error || res.statusText);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

function showToast(msg, ms = 3500) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add("hidden"), ms);
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMs(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function formatTs(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function showView(name) {
  $("#view-home").classList.toggle("hidden", name !== "home");
  $("#view-workspace").classList.toggle("hidden", name !== "workspace");
}

function isAlertsMuted() {
  return localStorage.getItem("gui_mute_alerts") === "1";
}

function setAlertsMuted(muted) {
  localStorage.setItem("gui_mute_alerts", muted ? "1" : "0");
  const btn = $("#btn-mute-alerts");
  if (btn) {
    btn.textContent = muted ? "Unmute alerts" : "Mute alerts";
    btn.classList.toggle("muted-active", muted);
  }
}

function playAttentionPing() {
  if (isAlertsMuted()) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.12;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
    osc.stop(ctx.currentTime + 0.25);
  } catch {
    /* Web Audio unavailable */
  }
}

function getBrowserApiGrants() {
  const grants = {};
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i);
    if (key?.startsWith(API_CONSENT_PREFIX)) {
      grants[key.slice(API_CONSENT_PREFIX.length)] = sessionStorage.getItem(key) === "1";
    }
  }
  return grants;
}

function setBrowserApiGrant(provider, granted) {
  sessionStorage.setItem(`${API_CONSENT_PREFIX}${provider}`, granted ? "1" : "0");
}

function mergedApiGrants() {
  return { ...state.apiConsent.grants, ...getBrowserApiGrants() };
}

function isProviderGranted(provider) {
  return Boolean(mergedApiGrants()[provider]);
}

async function loadApiConsent() {
  const data = await api("/api/session/api-consent");
  state.apiConsent.providers = data.providers || [];
  state.apiConsent.grants = { ...(data.grants || {}), ...getBrowserApiGrants() };
  renderApiConsentStrip();
}

function renderApiConsentStrip() {
  const strip = $("#api-consent-strip");
  if (!strip) return;
  const providers = state.apiConsent.providers || [];
  if (!providers.length) {
    strip.innerHTML = "";
    return;
  }
  strip.innerHTML = `<span class="muted">API access:</span>${providers
    .map((p) => {
      const ok = isProviderGranted(p.id);
      return `<span class="api-consent-chip ${ok ? "granted" : "pending"}">${escapeHtml(p.label)} ${ok ? "✓" : "—"}</span>`;
    })
    .join("")}`;
}

function revokeAllApiConsents() {
  for (const p of state.apiConsent.providers || []) {
    setBrowserApiGrant(p.id, false);
  }
  state.apiConsent.grants = {};
  renderApiConsentStrip();
  showToast("API access revoked for this browser session.");
}

function providersForExecute(body) {
  const stages = state.run?.stages || [];
  if (body.mode === "stage" && body.stage) {
    const s = stages.find((x) => x.id === body.stage);
    return s?.api_providers || [];
  }
  if (body.mode === "analysis") {
    const set = new Set();
    for (const s of stages) {
      if (s.phase === "analysis" && s.status === "pending" && s.api_providers) {
        s.api_providers.forEach((p) => set.add(p));
      }
    }
    return [...set];
  }
  const flowPhase = body.mode === "flow1" ? "flow1" : body.mode === "flow2" ? "flow2" : body.mode === "flow3" ? "flow3" : null;
  if (flowPhase) {
    const set = new Set();
    for (const s of stages) {
      if (s.phase === flowPhase && s.status === "pending" && s.api_providers) {
        s.api_providers.forEach((p) => set.add(p));
      }
    }
    return [...set];
  }
  return [];
}

function missingProvidersForExecute(body) {
  return providersForExecute(body).filter((p) => !isProviderGranted(p));
}

function showApiConsentModal(providerId) {
  return new Promise((resolve) => {
    const info = (state.apiConsent.providers || []).find((p) => p.id === providerId);
    const modal = $("#api-consent-modal");
    $("#api-consent-modal-title").textContent = info ? `Allow ${info.label}?` : "Allow external API?";
    $("#api-consent-modal-desc").textContent = info?.description || "";
    $("#api-consent-modal-cost").textContent = info?.cost_hint || "";
    modal.classList.remove("hidden");
    const onAllow = async () => {
      modal.classList.add("hidden");
      cleanup();
      setBrowserApiGrant(providerId, true);
      try {
        await api("/api/session/api-consent", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider: providerId, granted: true }),
        });
      } catch {
        /* sessionStorage is enough for this tab */
      }
      state.apiConsent.grants[providerId] = true;
      renderApiConsentStrip();
      resolve(true);
    };
    const onDeny = () => {
      modal.classList.add("hidden");
      cleanup();
      resolve(false);
    };
    const cleanup = () => {
      $("#btn-api-consent-allow").removeEventListener("click", onAllow);
      $("#btn-api-consent-deny").removeEventListener("click", onDeny);
    };
    $("#btn-api-consent-allow").addEventListener("click", onAllow);
    $("#btn-api-consent-deny").addEventListener("click", onDeny);
  });
}

async function ensureApiConsentForExecute(body) {
  const missing = missingProvidersForExecute(body);
  for (const pid of missing) {
    const ok = await showApiConsentModal(pid);
    if (!ok) return false;
  }
  return true;
}

function buildApiConsentsPayload() {
  const grants = mergedApiGrants();
  const out = {};
  for (const [k, v] of Object.entries(grants)) {
    if (v) out[k] = true;
  }
  return out;
}

function parseLogDetail(detail) {
  if (!detail) return null;
  if (typeof detail === "object") return detail;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function hasActionRequiredStage() {
  return (state.run?.stages || []).some((s) => s.status === "action_required");
}

function getHandoffPaths(stage) {
  const fromLog = findLatestHandoffForStage(stage.id);
  if (fromLog?.length) return fromLog;
  return [...(stage.artifacts_present || []), ...(stage.artifacts || [])].filter(
    (p, i, arr) => p && !p.endsWith("/") && arr.indexOf(p) === i,
  );
}

function findLatestHandoffForStage(stageId) {
  const entries = state.run?.log_tail || [];
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (e.stage !== stageId) continue;
    const d = parseLogDetail(e.detail);
    if (d?.handoff?.length) return d.handoff;
  }
  return null;
}

async function init() {
  state.config = await api("/api/config");
  setAlertsMuted(isAlertsMuted());
  await loadApiConsent();
  bindEvents();
  const session = await api("/api/session");
  if (session.log?.length) renderLog(session.log);
  if (session.active?.run_id) {
    state.selectedStageId = session.active.selected_stage_id || null;
    await openRun(session.active.run_id, { quiet: true });
  } else {
    await refreshHome();
  }
  startLogPoll();
}

function bindEvents() {
  $("#btn-refresh-assets").addEventListener("click", refreshHome);
  $("#btn-refresh-runs").addEventListener("click", refreshHome);
  $("#btn-home").addEventListener("click", goHome);
  $("#btn-mute-alerts")?.addEventListener("click", () => {
    setAlertsMuted(!isAlertsMuted());
  });
  $("#btn-revoke-api")?.addEventListener("click", revokeAllApiConsents);
  $("#btn-checkpoint-continue")?.addEventListener("click", onCheckpointContinue);
  $("#btn-handoff-ack")?.addEventListener("click", acknowledgeHandoff);
  $("#btn-run-next").addEventListener("click", runNextStage);
  $("#btn-run-analysis").addEventListener("click", () => executeJob({ mode: "analysis" }));
  $("#btn-reset-stage").addEventListener("click", redoFromStage);
  $("#btn-save-artifact").addEventListener("click", saveArtifact);
  $("#artifact-select").addEventListener("change", loadSelectedArtifact);
  $("#btn-save-profile").addEventListener("click", saveAnalysisProfile);
  $("#btn-verify-profile").addEventListener("click", verifyAnalysisProfile);
  $("#btn-reload-profile").addEventListener("click", loadAnalysisProfile);
  $("#nle-zoom").addEventListener("input", (e) => {
    state.zoom = Number(e.target.value);
    renderTimeline();
  });
  $("#btn-split").addEventListener("click", splitAtPlayhead);
  $("#btn-mark-redo").addEventListener("click", () => patchSelectedSegment({ mark_redo: true }));
  $("#btn-exclude").addEventListener("click", () => patchSelectedSegment({ excluded: true }));
  $("#btn-save-nle").addEventListener("click", saveNle);
  const player = $("#audio-player");
  player.addEventListener("timeupdate", () => {
    state.playheadMs = player.currentTime * 1000;
    updatePlayhead();
  });
}

async function goHome() {
  stopJobPoll();
  state.runId = null;
  showView("home");
  updateStatusBar(null);
  await refreshHome();
}

async function refreshHome() {
  const [assets, runs, session] = await Promise.all([
    api("/api/assets"),
    api("/api/runs"),
    api("/api/session").catch(() => ({})),
  ]);
  renderAssets(assets.files);
  renderRuns(runs.runs);
  const preview = $("#home-log-preview");
  const tailEl = $("#home-log-tail");
  if (session.log?.length && preview && tailEl) {
    preview.classList.remove("hidden");
    const tail = session.log.slice(-5);
    tailEl.innerHTML = tail
      .map(
        (e) =>
          `<div class="log-entry level-${e.level || "info"}"><span class="log-ts">${formatTs(e.ts)}</span> <span class="log-msg">${escapeHtml(e.message)}</span></div>`,
      )
      .join("");
  } else if (preview) {
    preview.classList.add("hidden");
  }
}

function renderAssets(files) {
  const el = $("#assets-list");
  if (!files.length) {
    el.innerHTML = `<p class="empty-state">No input audio in ASSETS/ (outside executions/). Add .wav files and refresh.</p>`;
    return;
  }
  el.innerHTML = files
    .map(
      (f) => `
    <div class="asset-item${state.selectedAsset === f.path ? " selected" : ""}" data-path="${f.path}">
      <div>
        <strong>${f.name}</strong>
        <div class="asset-meta">${f.path} · ${formatBytes(f.size_bytes)}</div>
      </div>
      <button class="btn primary sm btn-start" type="button">New execution</button>
    </div>`
    )
    .join("");

  el.querySelectorAll(".asset-item").forEach((item) => {
    item.addEventListener("click", (e) => {
      if (e.target.classList.contains("btn-start")) startRun(item.dataset.path);
      else {
        state.selectedAsset = item.dataset.path;
        renderAssets(files);
      }
    });
  });
}

function renderRuns(runs) {
  const el = $("#runs-list");
  if (!runs.length) {
    el.innerHTML = `<p class="empty-state">No executions yet. Start one from input audio.</p>`;
    return;
  }
  el.innerHTML = runs
    .map((r) => {
      const prog = r.progress ? `${r.progress.done}/${r.progress.total} stages` : "";
      const pct =
        r.progress?.total > 0 ? Math.round((100 * r.progress.done) / r.progress.total) : 0;
      const lastLog = r.last_log?.message ? escapeHtml(r.last_log.message).slice(0, 120) : "";
      const outs = (r.outputs || []).map((o) => o.split("/").pop()).join(", ");
      return `
    <div class="run-item" data-run="${r.run_id}">
      <div class="run-main">
        <strong>#${r.execution_number ?? "?"} · ${r.run_id}</strong>
        <div class="asset-meta">${formatTs(r.updated_at || r.created_at)}</div>
        <div class="asset-meta">${r.input_audio_path || ""}</div>
        <div class="asset-meta">${prog} (${pct}%)${r.selected_flow ? ` · ${r.selected_flow}` : ""}${outs ? ` · out: ${outs}` : ""}</div>
        ${lastLog ? `<div class="asset-meta muted">Last: ${lastLog}</div>` : ""}
      </div>
      <button class="btn primary sm" type="button">Resume</button>
    </div>`;
    })
    .join("");

  el.querySelectorAll(".run-item").forEach((item) => {
    item.addEventListener("click", () => openRun(item.dataset.run));
  });
}

async function startRun(inputPath) {
  try {
    const res = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input_audio_path: inputPath }),
    });
    appendClientLog(`Created execution ${res.run_id}`, "success");
    await openRun(res.run_id);
  } catch (e) {
    showToast(e.message);
  }
}

async function openRun(runId, opts = {}) {
  state.runId = runId;
  showView("workspace");
  await api("/api/session/active", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, selected_stage_id: state.selectedStageId }),
  });
  await refreshRun();
  if (!opts.quiet) appendClientLog(`Opened execution ${runId}`, "info");
  startJobPoll();
}

async function refreshRun() {
  if (!state.runId) return;
  state.run = await api(`/api/runs/${state.runId}`);
  state.shownPrecleanOffers = new Set(state.run?.meta?.audio_preclean?.offered_at || []);
  state.timeline = await api(`/api/runs/${state.runId}/timeline`).catch(() => null);
  state.nle = state.timeline?.nle || null;
  state.zoom = state.nle?.zoom || 1;
  $("#nle-zoom").value = state.zoom;

  $("#input-label").textContent = state.run.meta?.input_audio_path || "";
  renderStages();
  renderTimeline();
  renderLog(state.run.log_tail || []);

  if (!state.selectedStageId && state.run.stages.length) {
    selectStage(findActiveStage()?.id || state.run.stages[0].id);
  } else if (state.selectedStageId) {
    selectStage(state.selectedStageId);
  }

  updateStatusBar(state.run);
  updateJobUI(state.run.job);
  renderCheckpointBanner();
}

function renderCheckpointBanner() {
  const banner = $("#checkpoint-banner");
  if (!banner) return;
  const job = state.run?.job;
  const actionStage = state.run?.stages?.find((s) => s.status === "action_required");
  if (job?.status === "gate" || job?.status === "needs_operator") {
    banner.textContent = job.message || "Your action is required before the pipeline can continue.";
    banner.classList.remove("hidden");
    if (state.jobStatusPrev !== job.status) playAttentionPing();
    return;
  }
  if (actionStage) {
    banner.textContent = `Checkpoint: ${actionStage.title} — complete the steps below, then continue.`;
    banner.classList.remove("hidden");
    if (state.lastActionRequiredId !== actionStage.id) {
      state.lastActionRequiredId = actionStage.id;
      playAttentionPing();
    }
    return;
  }
  banner.classList.add("hidden");
  banner.textContent = "";
  state.lastActionRequiredId = null;
}

function updateStatusBar(run) {
  if (!run) {
    $("#status-execution").textContent = "—";
    $("#status-stage").textContent = "—";
    $("#status-job").textContent = "Idle";
    $("#status-job").className = "status-value idle";
    $("#status-updated").textContent = "—";
    updatePrecleanWarningsBanner(null);
    return;
  }
  const num = run.meta?.execution_number;
  $("#status-execution").textContent = num ? `#${num} · ${run.run_id}` : run.run_id;
  const stage = run.stages?.find((s) => s.id === state.selectedStageId);
  $("#status-stage").textContent = stage?.title || "—";
  $("#status-updated").textContent = formatTs(run.meta?.updated_at);
}

function renderLog(entries) {
  const el = $("#prompt-log");
  if (!entries?.length) {
    el.innerHTML = `<p class="log-empty">Log entries appear here as the pipeline runs.</p>`;
    state.logCount = 0;
    return;
  }
  el.innerHTML = entries
    .map(
      (e) => `
    <div class="log-entry level-${e.level || "info"}">
      <span class="log-ts">${formatTs(e.ts)}</span>
      ${e.stage ? `<span class="log-stage">[${e.stage}]</span>` : ""}
      <span class="log-msg">${escapeHtml(e.message)}</span>
      ${e.detail ? `<div class="log-detail">${escapeHtml(typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail))}</div>` : ""}
    </div>`
    )
    .join("");
  const prevCount = state.logCount;
  state.logCount = entries.length;
  el.scrollTop = el.scrollHeight;
  updateAlerts(entries);
  if (entries.length > prevCount) {
    const newest = entries[entries.length - 1];
    if (newest.level === "action" && newest.ts !== state.lastNotifiedTs) {
      state.lastNotifiedTs = newest.ts;
      playAttentionPing();
    }
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function updateAlerts(entries) {
  const alerts = entries.filter((e) => ["action", "warning", "error"].includes(e.level)).slice(-5);
  const strip = $("#alert-strip");
  const badge = $("#alert-badge");
  if (!alerts.length) {
    strip.classList.add("hidden");
    badge.classList.add("hidden");
    return;
  }
  badge.textContent = String(alerts.length);
  badge.classList.remove("hidden");
  strip.classList.remove("hidden");
  strip.innerHTML = alerts
    .map((a) => `<div class="alert-item level-${a.level}">${escapeHtml(a.message)}</div>`)
    .join("");
}

function appendClientLog(message, level = "info") {
  if (!state.runId) {
    renderLog([{ ts: new Date().toISOString(), level, message }]);
    return;
  }
  api(`/api/runs/${state.runId}/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, level }),
  }).then(() => pollLog());
}

function startLogPoll() {
  stopLogPoll();
  state.logPoll = setInterval(pollLog, 2000);
}

function stopLogPoll() {
  if (state.logPoll) {
    clearInterval(state.logPoll);
    state.logPoll = null;
  }
}

async function pollLog() {
  if (!state.runId) return;
  try {
    const data = await api(`/api/runs/${state.runId}/log?tail=200`);
    if (data.entries?.length !== state.logCount) {
      renderLog(data.entries);
      if (state.run) {
        state.run.log_tail = data.entries;
        const stage = state.run.stages?.find((s) => s.id === state.selectedStageId);
        if (stage) {
          renderHandoffPanel(stage);
          updateCheckpointContinue(stage);
        }
      }
    }
  } catch {
    /* ignore */
  }
}

function findActiveStage() {
  return (
    state.run.stages.find((s) => s.status === "action_required") ||
    state.run.stages.find((s) => s.status === "pending" && s.phase !== "gate")
  );
}

function renderStages() {
  const ol = $("#stage-list");
  ol.innerHTML = state.run.stages
    .map((s) => {
      const dot =
        s.status === "done"
          ? "done"
          : s.status === "action_required"
            ? "action_required"
            : s.status === "locked"
              ? "locked"
              : "pending";
      return `<li data-id="${s.id}" class="${s.id === state.selectedStageId ? "active" : ""}">
      <span class="stage-dot ${dot}"></span><span>${s.title}</span></li>`;
    })
    .join("");
  ol.querySelectorAll("li").forEach((li) => li.addEventListener("click", () => selectStage(li.dataset.id)));
}

async function selectStage(stageId) {
  state.selectedStageId = stageId;
  if (state.runId) {
    await api("/api/session/active", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: state.runId, selected_stage_id: stageId }),
    }).catch(() => {});
  }
  renderStages();
  const stage = state.run.stages.find((s) => s.id === stageId);
  if (!stage) return;
  $("#stage-title").textContent = stage.title;
  $("#stage-description").textContent = stage.description;
  updateStatusBar(state.run);
  await renderGateActions(stage);
  await renderLlmRoutingPanel(stage);
  renderCheckpoint(stage);
  renderHandoffPanel(stage);
  updateProfilePanelVisibility(stage);
  populateArtifactSelect(stage);
  if (stage.id === "analysis_profile") loadAnalysisProfile();
}

function renderCheckpoint(stage) {
  const panel = $("#checkpoint-panel");
  if (!panel) return;
  const needsPanel =
    stage.status === "action_required" ||
    state.run?.job?.status === "gate" ||
    state.run?.job?.status === "needs_operator" ||
    (stage.status === "done" && getHandoffPaths(stage).length && !state.run?.handoff_ack?.[stage.id]);
  panel.classList.toggle("hidden", !needsPanel);
  updateCheckpointContinue(stage);
}

function updateCheckpointContinue(stage) {
  const btn = $("#btn-checkpoint-continue");
  const summary = $("#checkpoint-summary");
  if (!btn || !summary) return;
  let enabled = false;
  let text = "";

  if (state.run?.job?.status === "needs_operator" && state.run.job.message?.includes("API consent")) {
    text = state.run.job.message;
  } else if (state.run?.job?.status === "gate") {
    text = state.run.job.message || "Complete the checkpoint below.";
  } else if (stage.status === "action_required") {
    text = `${stage.title}: complete the required actions below.`;
    if (stage.id === "g1_vo_pickup") enabled = Boolean(state.run?.g1_clear);
    else if (stage.id === "analysis_profile") enabled = Boolean(state.run?.profile_verified);
    else if (stage.id === "transcript_review") {
      text += " Use Complete transcript review when finished.";
    } else if (stage.id === "g2_flow_select") {
      text += " Choose a flow below.";
    }
  } else if (stage.status === "done") {
    const paths = getHandoffPaths(stage);
    if (paths.length && !state.run?.handoff_ack?.[stage.id]) {
      text = "Review output files in the handoff panel. Edit if needed, then acknowledge to continue.";
      enabled = true;
    }
  }

  summary.textContent = text;
  btn.disabled = !enabled;
}

async function onCheckpointContinue() {
  const stage = state.run?.stages?.find((s) => s.id === state.selectedStageId);
  if (!stage) return;
  if (stage.status === "done" && getHandoffPaths(stage).length) {
    await acknowledgeHandoff();
    return;
  }
  if (stage.id === "g1_vo_pickup" && state.run?.g1_clear) {
    selectStage("g2_flow_select");
    return;
  }
  await runNextStage();
}

async function acknowledgeHandoff() {
  if (!state.selectedStageId || !state.runId) return;
  await api(`/api/runs/${state.runId}/handoff-ack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage_id: state.selectedStageId }),
  });
  showToast("Handoff acknowledged.");
  await refreshRun();
}

function renderHandoffPanel(stage) {
  const panel = $("#handoff-panel");
  const list = $("#handoff-list");
  if (!panel || !list) return;
  const paths = getHandoffPaths(stage);
  const audit = findLatestHandoffAudit(stage.id);
  if (!paths.length && !audit) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const editableSet = new Set(stage.editable || []);
  list.innerHTML = paths
    .map((p) => {
      const ed = editableSet.has(p) ? '<span class="hint">editable</span>' : "";
      return `<li class="handoff-item"><code>${escapeHtml(p)}</code> ${ed}
        <span class="handoff-actions">
          <button type="button" class="btn ghost sm btn-handoff-open" data-path="${p.replace(/"/g, "&quot;")}">Open</button>
          <button type="button" class="btn ghost sm btn-handoff-copy" data-path="${p.replace(/"/g, "&quot;")}">Copy path</button>
        </span></li>`;
    })
    .join("");
  if (audit) {
    list.innerHTML += `<li class="handoff-item muted">LLM audit: <code>${escapeHtml(audit)}</code></li>`;
  }
  list.querySelectorAll(".btn-handoff-open").forEach((btn) => {
    btn.addEventListener("click", () => {
      const path = btn.dataset.path;
      const sel = $("#artifact-select");
      if ([...sel.options].some((o) => o.value === path)) {
        sel.value = path;
        loadSelectedArtifact();
      } else {
        showToast(`Add ${path} to editor after stage lists it.`);
      }
    });
  });
  list.querySelectorAll(".btn-handoff-copy").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigator.clipboard?.writeText(btn.dataset.path);
      showToast("Path copied.");
    });
  });
}

function findLatestHandoffAudit(stageId) {
  const entries = state.run?.log_tail || [];
  for (let i = entries.length - 1; i >= 0; i--) {
    const e = entries[i];
    if (e.stage !== stageId) continue;
    const d = parseLogDetail(e.detail);
    if (d?.audit_path) return d.audit_path;
  }
  return null;
}

function updateProfilePanelVisibility(stage) {
  const panel = $("#profile-panel");
  const show =
    stage?.id === "analysis_profile" ||
    (state.run?.stages?.find((s) => s.id === "analysis_profile")?.status !== "locked");
  panel.classList.toggle("hidden", !show);
}

async function renderLlmRoutingPanel(stage) {
  const el = $("#llm-routing-panel");
  if (!el || !state.runId) return;
  el.innerHTML = "";
  el.classList.add("hidden");
  const llmStages = new Set([
    "speaker_roles",
    "content_context",
    "boundary_detection",
    "segment_classification",
    "missing_framing",
    "optimal_questions",
    "topic_coverage_audit",
    "narrative_arc_plan",
    "full_master_ranking",
    "highlight_selection",
    "transitions",
    "podcast_show_description",
  ]);
  if (!llmStages.has(stage.id)) return;
  try {
    const data = await api(`/api/runs/${state.runId}/llm-routing`);
    const rows = (data.attempts || []).filter((a) => a.stage === stage.id);
    if (!rows.length) return;
    el.classList.remove("hidden");
    const lines = rows.map(
      (r) =>
        `<li><code>${r.task_kind || "primary"}</code> verdict=<strong>${r.verdict || "—"}</strong> shards=${r.shard_count || 0} trunc=${(r.truncation_flags || []).join(",") || "none"}</li>`,
    );
    el.innerHTML = `<p class="hint"><strong>LLM routing</strong></p><ul class="llm-routing-list">${lines.join("")}</ul>`;
  } catch {
    /* panel optional */
  }
}

async function renderGateActions(stage) {
  const el = $("#gate-actions");
  el.innerHTML = "";

  const audioOutputs = stage.audio_outputs_present || [];
  if (audioOutputs.length) {
    const listen = document.createElement("div");
    listen.className = "stage-audio-actions";
    listen.innerHTML = `<p class="hint"><strong>Listen</strong> stage output audio:</p>`;
    audioOutputs.forEach((path) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost sm";
      btn.textContent = `Listen ${path.split("/").pop()}`;
      btn.addEventListener("click", () => {
        const player = $("#audio-player");
        const url = `/api/runs/${state.runId}/audio?path=${encodeURIComponent(path)}`;
        player.src = url;
        player.setAttribute("data-src", url);
        player.currentTime = 0;
        player.play().catch(() => {});
      });
      listen.appendChild(btn);
    });
    el.appendChild(listen);
  }

  if (stage.id === "analysis_profile") {
    const verified = stage.status === "done";
    const flow1Block =
      state.run?.selected_flow === "flow1" && state.run?.profile_gate_pending;
    const copy = document.createElement("div");
    copy.innerHTML = `<p class="hint">Review themes, major questions, and style in the <strong>Interview profile</strong> panel below. Mark verified when the profile matches your intent for this recording.</p>
      <p class="muted">${verified ? "Profile marked verified." : "Not verified yet — AI stages still treat profile as draft."}</p>
      ${
        flow1Block
          ? "<p class=\"hint\"><strong>Flow 1 extended</strong> (topic coverage and later) is blocked until you mark the profile verified.</p>"
          : ""
      }`;
    el.appendChild(copy);
    await renderPrecleanOffer(stage, el);
    return;
  }

  if (
    stage.id === "topic_coverage_audit" &&
    stage.status === "locked" &&
    state.run?.profile_gate_pending
  ) {
    el.innerHTML = `<p class="hint"><strong>Profile gate:</strong> verify the interview profile before Flow 1 extended analysis. Open <strong>Interview profile</strong> in the stage list, edit themes and style, then click <strong>Mark profile verified</strong>.</p>`;
    return;
  }

  if (stage.id === "transcript_review" && stage.status === "action_required") {
    renderTranscriptReviewPanel(el);
    return;
  }

  if (stage.id === "g1_vo_pickup" && stage.status === "done") {
    el.innerHTML = `<p class="hint">All pickup lines recorded. Optional: clean new VO files before ingest, or continue to flow selection.</p>`;
    await renderPrecleanOffer(stage, el);
    return;
  }

  if (stage.id === "g1_vo_pickup" && stage.status === "action_required") {
    el.innerHTML = `<p class="hint">Record or upload pickup lines. Saved to <code>ASSETS/executions/…/vo_pickup/</code></p>`;
    (state.timeline?.vo_lines || [])
      .filter((l) => l.delivery === "record")
      .forEach((line) => {
        const card = document.createElement("div");
        card.className = "vo-card";
        const recorded = line.recorded_file ? `✓ ${line.recorded_file}` : "Missing";
        card.innerHTML = `
          <h4>${line.line_id} → ${line.targets_segment_id}</h4>
          <p>${line.text}</p>
          <p class="muted">${line.gap_type} · ${recorded}</p>
          <div class="vo-actions">
            <button class="btn sm btn-record" data-line="${line.line_id}" type="button">Record</button>
            <button class="btn sm ghost btn-stop-record hidden" data-line="${line.line_id}" type="button">Stop</button>
            <input type="file" accept="audio/*" class="vo-upload" data-line="${line.line_id}" />
          </div>`;
        el.appendChild(card);
      });
    wireVoControls(el);
    if (!(state.run.g1_missing || []).length) {
      const btn = document.createElement("button");
      btn.className = "btn primary";
      btn.textContent = "All VO recorded — continue";
      btn.onclick = () => executeJob({ mode: "stage", stage: "vo_ingest" });
      el.appendChild(btn);
    }
  }

  if (stage.id === "g2_flow_select" && stage.status === "action_required") {
    el.innerHTML = `<p class="hint">Choose deliverable flow.</p>
      <div class="flow-choice">
        <button class="btn primary" data-flow="flow1" type="button">Flow 1 — Full podcast</button>
        <button class="btn primary" data-flow="flow2" type="button">Flow 2 — Highlight reel</button>
        <button class="btn primary" data-flow="flow3" type="button">Flow 3 — Show description</button>
      </div>`;
    el.querySelectorAll("[data-flow]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(`/api/runs/${state.runId}/flow`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ flow: btn.dataset.flow }),
        });
        await refreshRun();
      });
    });
  }

  if (stage.id === "assembly_preview") {
    await renderPrecleanOffer(stage, el);
  }

  if (stage.id === "source_acoustic_profile") {
    const btn = document.createElement("button");
    btn.className = "btn sm primary";
    btn.type = "button";
    btn.textContent = "Recompute profile";
    btn.onclick = async () => {
      if (!confirm("Recompute acoustic profile from current ingest/transcript?")) return;
      await api(`/api/runs/${state.runId}/recompute-acoustic-profile`, { method: "POST" });
      showToast("Acoustic profile recomputed.");
      await refreshRun();
    };
    el.appendChild(btn);
    await renderAcousticProfileOverridesPanel(el);
  }

  if (stage.id === "full_master_ranking" || stage.id === "edl_flow1") {
    renderQcSummaryCard(el, "narrative_qc");
  }

  if (stage.id === "podcast_show_description") {
    renderQcSummaryCard(el, "show_description_qc");
  }

  if (stage.id === "content_context" && (state.config?.value_analysis_enabled || state.run?.meta?.qc_summaries)) {
    await renderValueFeaturesPanel(el);
  }

  if (stage.id === "elevenlabs_prompt_craft") {
    await renderElevenLabsPromptReviewPanel(el);
    await renderElevenLabsPostListenPanel(el, stage);
    return;
  }

  if (stage.id === "elevenlabs_sfx_flow1" || stage.id === "elevenlabs_sfx_flow2") {
    const review = await api(`/api/runs/${state.runId}/elevenlabs-prompts`).catch(() => null);
    if (review?.review_required && review?.can_generate === false) {
      el.innerHTML = `<div class="quality-offer-card">
        <p class="hint"><strong>G1.5 required:</strong> review and approve ElevenLabs prompts before generation.</p>
        <p class="muted">Open <strong>ElevenLabs prompt craft</strong> to edit prompts, tune influence, and approve.</p>
        <div class="flow-choice">
          <button class="btn primary sm" type="button" id="btn-open-prompt-review">Open prompt craft</button>
        </div>
      </div>`;
      el.querySelector("#btn-open-prompt-review")?.addEventListener("click", () => {
        selectStage("elevenlabs_prompt_craft");
      });
      return;
    }
    await renderElevenLabsPostListenPanel(el, stage);
  }

  await renderPrecleanOffer(stage, el);
}

const VALUE_FEATURES_PATH = "understanding/value_features.json";
const SAP_PATH = "understanding/source_acoustic_profile.json";

const PACE_CLASS_OPTIONS = ["", "calm", "conversational", "brisk", "dense"];
const UNDERSCORE_POLICY_OPTIONS = ["", "normal", "sparse", "skip"];

async function renderAcousticProfileOverridesPanel(host) {
  const card = document.createElement("div");
  card.className = "quality-offer-card acoustic-overrides-card";
  card.innerHTML = `<h4>Operator overrides</h4>
    <p class="muted">Tune pace and underscore policy without re-running DSP. Leave blank to use derived values.</p>`;
  host.appendChild(card);

  let profile;
  try {
    profile = await api(
      `/api/runs/${state.runId}/artifact?path=${encodeURIComponent(SAP_PATH)}`,
    );
  } catch {
    card.innerHTML += `<p class="hint">Run <strong>Source acoustic profile</strong> first.</p>`;
    return;
  }

  const derivedPace = profile?.pacing?.pace_class || "—";
  const derivedPolicy = profile?.mix_contract?.underscore_policy || "—";
  const overrides = profile?.operator_overrides && typeof profile.operator_overrides === "object"
    ? profile.operator_overrides
    : {};
  const paceOverride = overrides?.pacing?.pace_class || "";
  const policyOverride = overrides?.mix_contract?.underscore_policy || "";

  const form = document.createElement("div");
  form.className = "acoustic-overrides-form";
  form.innerHTML = `
    <label class="tr-label">pace_class <span class="muted">(derived: ${escapeHtml(derivedPace)})</span>
      <select id="sap-override-pace" class="select">
        ${PACE_CLASS_OPTIONS.map(
          (v) => `<option value="${v}"${v === paceOverride ? " selected" : ""}>${v || "— use derived —"}</option>`,
        ).join("")}
      </select>
    </label>
    <label class="tr-label">underscore_policy <span class="muted">(derived: ${escapeHtml(derivedPolicy)})</span>
      <select id="sap-override-underscore" class="select">
        ${UNDERSCORE_POLICY_OPTIONS.map(
          (v) =>
            `<option value="${v}"${v === policyOverride ? " selected" : ""}>${v || "— use derived —"}</option>`,
        ).join("")}
      </select>
    </label>
    <div class="flow-choice">
      <button type="button" class="btn primary sm" id="sap-save-overrides">Save overrides</button>
      <button type="button" class="btn sm" id="sap-clear-overrides">Clear overrides</button>
    </div>
    <p id="sap-overrides-status" class="save-status"></p>`;
  card.appendChild(form);

  const statusEl = form.querySelector("#sap-overrides-status");

  async function saveOverrides(overrides) {
    const res = await api(`/api/runs/${state.runId}/acoustic-profile/overrides`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overrides }),
    });
    const eff = res?.effective || {};
    statusEl.textContent = `Saved — effective pace=${eff.pace_class || "—"} underscore=${eff.underscore_policy || "—"}`;
    showToast("Acoustic overrides saved");
    await refreshRun();
    if ($("#artifact-select")?.value === SAP_PATH) {
      await loadSelectedArtifact();
    }
  }

  form.querySelector("#sap-save-overrides")?.addEventListener("click", async () => {
    const pace = form.querySelector("#sap-override-pace")?.value || "";
    const policy = form.querySelector("#sap-override-underscore")?.value || "";
    const overrides = {};
    if (pace) overrides.pace_class = pace;
    if (policy) overrides.underscore_policy = policy;
    try {
      await saveOverrides(overrides);
    } catch (err) {
      statusEl.textContent = err?.message || "Save failed";
    }
  });

  form.querySelector("#sap-clear-overrides")?.addEventListener("click", async () => {
    if (!confirm("Clear all operator overrides and use derived values?")) return;
    try {
      await saveOverrides({});
      form.querySelector("#sap-override-pace").value = "";
      form.querySelector("#sap-override-underscore").value = "";
    } catch (err) {
      statusEl.textContent = err?.message || "Clear failed";
    }
  });
}

function renderQcSummaryCard(host, key) {
  const summary = state.run?.meta?.qc_summaries?.[key];
  if (!summary) return;
  const card = document.createElement("div");
  card.className = `qc-summary-card ${summary.passed ? "qc-pass" : "qc-fail"}`;
  const label = key === "narrative_qc" ? "Flow 1 narrative QC" : "Show description QC";
  const errText =
    Array.isArray(summary.errors) && summary.errors.length
      ? `<ul>${summary.errors.slice(0, 4).map((e) => `<li>${e}</li>`).join("")}</ul>`
      : "";
  card.innerHTML = `<h4>${label}</h4><p>${summary.passed ? "Pass" : "Fail"}${summary.strict ? " (strict)" : ""}</p>${errText}`;
  host.appendChild(card);
}

function nleHasOperatorEdits(nle) {
  if (!nle || typeof nle !== "object") return false;
  const order = nle.sequence_order;
  if (Array.isArray(order) && order.length) return true;
  const overrides = nle.segment_overrides;
  if (!overrides || typeof overrides !== "object") return false;
  return Object.values(overrides).some((ov) => {
    if (!ov || typeof ov !== "object") return false;
    return ov.excluded || ov.mark_redo || ov.start_ms != null || ov.end_ms != null || ov.split_into;
  });
}

function formatValueMetric(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

function formatValueTags(tags) {
  if (!tags || typeof tags !== "object") return [];
  return ["LEX", "COM", "CRE"].flatMap((axis) => {
    const items = tags[axis];
    if (!Array.isArray(items) || !items.length) return [];
    return items.map((t) => `${axis}:${t}`);
  });
}

async function renderValueFeaturesPanel(host) {
  const card = document.createElement("div");
  card.className = "quality-offer-card value-features-card";
  card.innerHTML = `<h4>Value features</h4>
    <p class="muted">Deterministic metrics when value_analysis is enabled.</p>`;
  host.appendChild(card);

  let data;
  try {
    data = await api(
      `/api/runs/${state.runId}/artifact?path=${encodeURIComponent(VALUE_FEATURES_PATH)}`,
    );
  } catch {
    card.innerHTML += `<p class="hint">No <code>${VALUE_FEATURES_PATH}</code> yet. With <code>value_analysis.enabled</code> in config, run:</p>
      <p class="hint"><code>python tools/extract_value_features.py --run-id ${state.runId} --profile all</code></p>`;
    return;
  }

  const profiles = data?.profiles && typeof data.profiles === "object" ? data.profiles : {};
  const rows = [];
  const tr = profiles.transcript;
  if (tr && typeof tr === "object") {
    rows.push(
      ["Transcript · WPM proxy", tr.words_per_minute_proxy],
      ["Transcript · median pause (ms)", tr.median_pause_ms],
      ["Transcript · segments", tr.segment_count],
      ["Transcript · segment p50 / p90", `${formatValueMetric(tr.segment_length_p50)} / ${formatValueMetric(tr.segment_length_p90)}`],
      ["Transcript · interviewer turn ratio", tr.interviewer_turn_ratio],
      ["Transcript · tags", formatValueTags(tr.tags).join(", ") || "—"],
    );
  }
  const au = profiles.audio;
  if (au && typeof au === "object") {
    rows.push(
      ["Audio · duration (s)", au.duration_sec],
      ["Audio · silence ratio", au.silence_ratio],
      ["Audio · RMS p50 / p90", `${formatValueMetric(au.rms_p50)} / ${formatValueMetric(au.rms_p90)}`],
      ["Audio · peak dBFS proxy", au.peak_dbfs_proxy],
    );
  }

  if (!rows.length) {
    card.innerHTML += `<p class="hint"><code>${VALUE_FEATURES_PATH}</code> exists but has no profiles — re-run the extractor.</p>`;
    return;
  }

  const dl = document.createElement("dl");
  dl.className = "value-features-dl";
  rows.forEach(([label, value]) => {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = formatValueMetric(value);
    dl.appendChild(dt);
    dl.appendChild(dd);
  });
  card.appendChild(dl);
  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `run_id ${data.run_id || state.runId} · ${VALUE_FEATURES_PATH}`;
  card.appendChild(meta);
}

async function renderElevenLabsPromptReviewPanel(host) {
  const data = await api(`/api/runs/${state.runId}/elevenlabs-prompts`);
  const prompts = Array.isArray(data.prompts) ? data.prompts : [];
  const approved = Boolean(data.review?.approved);
  const reviewRequired = Boolean(data.review_required);
  const warnings = Array.isArray(data.warnings) ? data.warnings : [];
  const warningsHtml = warnings.length
    ? `<ul class="muted">${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`
    : "";
  host.innerHTML = `
    <div class="quality-offer-card">
      <p class="hint"><strong>G1.5 prompt review:</strong> review or edit crafted prompts before SFX generation.</p>
      <p class="muted">Approval status: ${
        approved
          ? `approved by ${escapeHtml(data.review?.approved_by || "operator")} at ${formatTs(data.review?.approved_at)}`
          : "pending approval"
      }${reviewRequired ? " (required before generate)" : " (optional)"}.</p>
    </div>
    <div id="el-prompt-list"></div>
    ${warningsHtml}
    <div class="flow-choice">
      <button class="btn ghost sm" type="button" id="btn-el-save-prompts">Save edits</button>
      <button class="btn primary sm" type="button" id="btn-el-approve-prompts" ${prompts.length ? "" : "disabled"}>Approve prompts</button>
    </div>
  `;
  const list = host.querySelector("#el-prompt-list");
  if (!prompts.length) {
    list.innerHTML = `<p class="empty-state">No crafted prompts yet. Run this stage first.</p>`;
  } else {
    list.innerHTML = prompts
      .map((row, idx) => {
        const aid = escapeHtml(row.asset_id || `asset_${idx + 1}`);
        const role = escapeHtml(row.role || "unknown");
        const duration = Number(row.duration_seconds || 0);
        const influence = Number(row.prompt_influence ?? 0.35);
        return `<div class="vo-card" data-idx="${idx}">
          <h4>${aid} · ${role}</h4>
          <div class="asset-meta">duration ${duration.toFixed(2)}s</div>
          <label class="tr-label">Prompt influence (0–1)</label>
          <input class="input el-prompt-influence" type="number" min="0" max="1" step="0.05" value="${influence.toFixed(2)}" />
          <label class="tr-label">Prompt</label>
          <textarea class="tr-textarea el-prompt-text" rows="3">${escapeHtml(row.elevenlabs_prompt || "")}</textarea>
          <label class="tr-label">Negative prompt</label>
          <input class="input el-negative-prompt" value="${escapeHtml(row.negative_prompt || "")}" />
        </div>`;
      })
      .join("");
  }

  host.querySelector("#btn-el-save-prompts")?.addEventListener("click", async () => {
    const next = collectElevenLabsPromptEdits(prompts, host);
    await api(`/api/runs/${state.runId}/elevenlabs-prompts`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: "sound_design/elevenlabs_prompts.json",
        data: { prompts: next },
        invalidate_from: "elevenlabs_prompt_craft",
      }),
    });
    showToast("Prompt edits saved; approval reset.");
    await refreshRun();
    await selectStage("elevenlabs_prompt_craft");
  });

  host.querySelector("#btn-el-approve-prompts")?.addEventListener("click", async () => {
    await api(`/api/runs/${state.runId}/elevenlabs-prompts/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: "operator_gui" }),
    });
    showToast("Prompts approved.");
    await refreshRun();
    await selectStage("elevenlabs_prompt_craft");
  });
}

function latestElevenLabsListenByAsset(listenResults) {
  const map = new Map();
  for (const row of listenResults || []) {
    if (row?.asset_id) map.set(row.asset_id, row);
  }
  return map;
}

function collectElevenLabsGeneratedAssets(stage) {
  const paths = new Map();
  for (const a of state.run?.elevenlabs_generated_assets || []) {
    if (a?.asset_id) {
      paths.set(a.asset_id, a.path || `sound_design/assets/${a.asset_id}.wav`);
    }
  }
  for (const p of stage?.audio_outputs_present || []) {
    if (!/\.wav$/i.test(p)) continue;
    const base = p.split("/").pop().replace(/\.wav$/i, "");
    if (!paths.has(base)) paths.set(base, p);
  }
  return [...paths.entries()].map(([asset_id, path]) => ({ asset_id, path }));
}

async function submitElevenLabsListenResult(assetId, result, note) {
  const body = { asset_id: assetId, result };
  if (note?.trim()) body.note = note.trim();
  await api(`/api/runs/${state.runId}/elevenlabs-prompts/listen-result`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  showToast(`Post-listen: ${assetId} → ${result}`);
  await refreshRun();
  await pollLog();
}

async function renderElevenLabsPostListenPanel(host, stage) {
  const assets = collectElevenLabsGeneratedAssets(stage);
  if (!assets.length) return;

  host.classList.remove("hidden");
  const listenResults = state.run?.meta?.elevenlabs_listen_results || [];
  const latest = latestElevenLabsListenByAsset(listenResults);

  const wrap = document.createElement("div");
  wrap.className = "quality-offer-card el-post-listen-card";
  wrap.innerHTML = `<h4>Post-listen QA (advisory)</h4>
    <p class="muted">Listen to each generated asset, then record pass or fail. Optional note is stored in <code>run_meta.json</code> and the log panel.</p>`;

  for (const { asset_id, path } of assets) {
    const prev = latest.get(asset_id);
    const prevHtml = prev
      ? `Last: <strong>${escapeHtml(prev.result)}</strong> at ${formatTs(prev.at)}${
          prev.note ? ` — ${escapeHtml(prev.note)}` : ""
        }`
      : "Not reviewed yet";
    const card = document.createElement("div");
    card.className = "vo-card el-post-listen-row";
    card.innerHTML = `
      <h4>${escapeHtml(asset_id)}</h4>
      <p class="muted"><code>${escapeHtml(path)}</code> · <span class="el-post-listen-status">${prevHtml}</span></p>
      <div class="stage-audio-actions flow-choice">
        <button type="button" class="btn ghost sm btn-el-listen">Listen</button>
        <button type="button" class="btn primary sm btn-el-pass">Pass</button>
        <button type="button" class="btn ghost sm btn-el-fail">Fail</button>
      </div>
      <label class="tr-label">Note (optional)</label>
      <input type="text" class="input el-post-listen-note" placeholder="e.g. vocals in tail" />
    `;
    card.querySelector(".btn-el-listen")?.addEventListener("click", () => {
      const player = $("#audio-player");
      const url = `/api/runs/${state.runId}/audio?path=${encodeURIComponent(path)}`;
      player.src = url;
      player.setAttribute("data-src", url);
      player.currentTime = 0;
      player.play().catch(() => {});
    });
    card.querySelector(".btn-el-pass")?.addEventListener("click", async () => {
      const note = card.querySelector(".el-post-listen-note")?.value || "";
      await submitElevenLabsListenResult(asset_id, "pass", note);
      await renderGateActions(stage);
    });
    card.querySelector(".btn-el-fail")?.addEventListener("click", async () => {
      const note = card.querySelector(".el-post-listen-note")?.value || "";
      await submitElevenLabsListenResult(asset_id, "fail", note);
      await renderGateActions(stage);
    });
    wrap.appendChild(card);
  }

  if (listenResults.length) {
    const hist = document.createElement("div");
    hist.className = "el-post-listen-history";
    hist.innerHTML = `<h4 class="muted">Listen history (read-only)</h4>
      <ul class="muted">${[...listenResults]
        .reverse()
        .map((e) => {
          const note = e.note ? ` — ${escapeHtml(e.note)}` : "";
          return `<li>${formatTs(e.at)} · <strong>${escapeHtml(e.asset_id)}</strong> · ${escapeHtml(e.result)}${note}</li>`;
        })
        .join("")}</ul>`;
    wrap.appendChild(hist);
  }

  host.appendChild(wrap);
}

function collectElevenLabsPromptEdits(originalRows, host) {
  return originalRows.map((row, idx) => {
    const card = host.querySelector(`.vo-card[data-idx="${idx}"]`);
    if (!card) return row;
    const promptText = card.querySelector(".el-prompt-text")?.value || "";
    const negative = card.querySelector(".el-negative-prompt")?.value || "";
    const influenceRaw = card.querySelector(".el-prompt-influence")?.value;
    const influence = influenceRaw !== undefined && influenceRaw !== "" ? Number(influenceRaw) : row.prompt_influence;
    return {
      ...row,
      elevenlabs_prompt: promptText.trim(),
      negative_prompt: negative.trim(),
      prompt_influence: Number.isFinite(influence) ? Math.min(1, Math.max(0, influence)) : row.prompt_influence,
    };
  });
}

async function renderPrecleanOffer(stage, host) {
  const offer = resolvePrecleanOffer(stage);
  if (!offer || !state.runId) return;
  host.classList.remove("hidden");
  await announcePrecleanOffer(offer.checkpoint);
  const card = document.createElement("div");
  card.className = "quality-offer-card";
  card.innerHTML = `<p class="hint"><strong>Quality offer:</strong> ${offer.prompt}</p>
    <p class="muted">Scope: <code>${offer.scope}</code>. Optional, non-blocking, and never auto-runs.</p>
    <div class="flow-choice">
      <button class="btn ghost sm" type="button" data-action="dismiss">Dismiss</button>
      <button class="btn primary sm" type="button" data-action="accept">Accept</button>
    </div>`;
  host.appendChild(card);
  card.querySelectorAll("[data-action]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api(`/api/runs/${state.runId}/preclean-offer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          checkpoint: offer.checkpoint,
          action: btn.dataset.action,
          scope: offer.scope,
        }),
      });
      if (btn.dataset.action === "accept" && offer.checkpoint === "g1_vo_pickup") {
        showToast("Running pickup pre-clean…");
        await executeJob({ mode: "stage", stage: "audio_preclean" });
      } else {
        showToast(
          btn.dataset.action === "accept"
            ? `Saved pre-clean preference (${offer.scope}).`
            : "Pre-clean offer dismissed."
        );
      }
      await refreshRun();
    })
  );
}

function resolvePrecleanOffer(stage) {
  if (stage.id === "audio_preclean") {
    return {
      checkpoint: "before_ingest",
      scope: "full_source",
      prompt: "Clean source interview background noise before ingest?",
    };
  }
  if (stage.id === "transcript_review" && stage.status === "done") {
    return {
      checkpoint: "after_g0",
      scope: "full_source",
      prompt: "Re-clean full source if low-confidence transcript errors seem noise-related?",
    };
  }
  if (stage.id === "analysis_profile" || stage.id === "segment_classification") {
    return {
      checkpoint: "after_profile_or_segmentation",
      scope: "full_source",
      prompt: "Clean source audio before re-running analysis from ingest?",
    };
  }
  if (stage.id === "g1_vo_pickup" && stage.status === "done") {
    return {
      checkpoint: "g1_vo_pickup",
      scope: "vo_pickup",
      prompt: "Remove background noise from new pickup recordings?",
    };
  }
  if (stage.id === "mix_flow1" || stage.id === "mix_flow2" || stage.id === "mux_flow1" || stage.id === "mux_flow2") {
    return {
      checkpoint: "before_flow_mix",
      scope: "normalized_rebuild",
      prompt: "Clean normalized interview audio before final assembly/mix?",
    };
  }
  if (stage.id === "assembly_preview") {
    return {
      checkpoint: "before_sfx_spend",
      scope: "full_source",
      prompt: "Clean source before ElevenLabs SFX spend?",
    };
  }
  if (stage.id === "master_flow1" || stage.id === "master_flow2") {
    return {
      checkpoint: "before_master_export",
      scope: "normalized_rebuild",
      prompt: "Last chance: pre-clean before master export?",
    };
  }
  return null;
}

async function announcePrecleanOffer(checkpoint) {
  if (!checkpoint || state.shownPrecleanOffers.has(checkpoint)) return;
  await api(`/api/runs/${state.runId}/preclean-offer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ checkpoint, action: "offer" }),
  });
  state.shownPrecleanOffers.add(checkpoint);
}

async function renderTranscriptReviewPanel(el) {
  el.innerHTML = `<p class="hint">Clips are ranked lowest AWS confidence first. Listen, fix text, save each chunk, then complete review.</p>
    <div id="tr-review-panel" class="tr-review-loading muted">Loading review queue…</div>`;
  try {
    state.transcriptReview = await api(`/api/runs/${state.runId}/transcript-review`);
    state.transcriptReviewIndex = 0;
    paintTranscriptReviewUI(el);
  } catch (e) {
    el.querySelector("#tr-review-panel").textContent = e.message;
  }
}

function paintTranscriptReviewUI(el) {
  const data = state.transcriptReview;
  const chunks = data?.chunks || [];
  if (!chunks.length) {
    el.innerHTML = `<p class="empty-state">No review clips — run STT review prep first.</p>`;
    return;
  }
  const idx = Math.min(state.transcriptReviewIndex, chunks.length - 1);
  const chunk = chunks[idx];
  const confPct = Math.round((chunk.confidence || 0) * 100);
  const confClass = chunk.confidence < (data.low_confidence_threshold || 0.85) ? "low" : "ok";
  const clipUrl = chunk.clip_path
    ? `/api/runs/${state.runId}/audio?path=${encodeURIComponent(chunk.clip_path)}`
    : "";

  el.innerHTML = `
    <div class="tr-review-header">
      <span>Clip <strong>${idx + 1}</strong> of <strong>${chunks.length}</strong></span>
      <span class="tr-conf ${confClass}">Confidence ${confPct}%</span>
      <span class="muted">${chunk.chunk_id} · ${formatMs(chunk.start_ms)}–${formatMs(chunk.end_ms)} · ${chunk.speaker_id || "—"}</span>
      <span class="muted">${data.pending_count ?? 0} pending</span>
    </div>
    <div class="tr-review-nav">
      <button type="button" class="btn sm ghost" id="tr-prev" ${idx === 0 ? "disabled" : ""}>Previous</button>
      <button type="button" class="btn sm ghost" id="tr-next" ${idx >= chunks.length - 1 ? "disabled" : ""}>Next</button>
      <select id="tr-jump" class="select sm"></select>
    </div>
    <div class="tr-review-body">
      <audio id="tr-audio" controls class="audio-player" src="${clipUrl}"></audio>
      <label class="tr-label">Transcript (editable)</label>
      <textarea id="tr-text" class="tr-textarea" rows="5"></textarea>
      <div class="tr-review-actions">
        <button type="button" class="btn primary sm" id="tr-save">Save chunk</button>
        <button type="button" class="btn ghost sm" id="tr-skip">Mark reviewed (no change)</button>
      </div>
    </div>
    <div class="tr-review-footer">
      <button type="button" class="btn primary" id="tr-complete">Complete transcript review</button>
      <button type="button" class="btn ghost sm" id="tr-complete-all">Accept remaining &amp; complete</button>
    </div>`;

  const jump = el.querySelector("#tr-jump");
  jump.innerHTML = chunks
    .map(
      (c, i) =>
        `<option value="${i}" ${i === idx ? "selected" : ""}>#${c.rank} ${c.chunk_id}${c.reviewed ? " ✓" : ""} (${Math.round((c.confidence || 0) * 100)}%)</option>`
    )
    .join("");

  const ta = el.querySelector("#tr-text");
  if (ta) ta.value = chunk.corrected_text || chunk.text || "";

  el.querySelector("#tr-prev")?.addEventListener("click", () => {
    state.transcriptReviewIndex = Math.max(0, idx - 1);
    paintTranscriptReviewUI(el);
  });
  el.querySelector("#tr-next")?.addEventListener("click", () => {
    state.transcriptReviewIndex = Math.min(chunks.length - 1, idx + 1);
    paintTranscriptReviewUI(el);
  });
  jump.addEventListener("change", () => {
    state.transcriptReviewIndex = Number(jump.value);
    paintTranscriptReviewUI(el);
  });
  el.querySelector("#tr-save")?.addEventListener("click", () => saveTranscriptChunk(chunk.chunk_id, true));
  el.querySelector("#tr-skip")?.addEventListener("click", () =>
    saveTranscriptChunk(chunk.chunk_id, true, { useOriginal: true })
  );
  el.querySelector("#tr-complete")?.addEventListener("click", () => completeTranscriptReview(false));
  el.querySelector("#tr-complete-all")?.addEventListener("click", () => completeTranscriptReview(true));
}

async function saveTranscriptChunk(chunkId, reviewed, opts = {}) {
  const textarea = $("#tr-text");
  const chunk = (state.transcriptReview?.chunks || []).find((c) => c.chunk_id === chunkId);
  const text = opts.useOriginal ? chunk?.text || "" : textarea?.value || "";
  await api(`/api/runs/${state.runId}/transcript-review/${chunkId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, reviewed }),
  });
  showToast("Chunk saved");
  state.transcriptReview = await api(`/api/runs/${state.runId}/transcript-review`);
  const chunks = state.transcriptReview.chunks || [];
  const cur = chunks.findIndex((c) => c.chunk_id === chunkId);
  if (cur >= 0 && cur < chunks.length - 1) state.transcriptReviewIndex = cur + 1;
  const panel = $("#gate-actions");
  if (panel && !panel.classList.contains("hidden")) paintTranscriptReviewUI(panel);
  await refreshRun();
}

async function completeTranscriptReview(acceptUnreviewed) {
  try {
    await api(`/api/runs/${state.runId}/transcript-review/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accept_unreviewed: acceptUnreviewed }),
    });
    showToast("Transcript review complete");
    await refreshRun();
  } catch (e) {
    showToast(e.message);
  }
}

function wireVoControls(el) {
  el.querySelectorAll(".vo-upload").forEach((input) => {
    input.addEventListener("change", async () => {
      if (input.files[0]) await uploadVoFile(input.dataset.line, input.files[0]);
    });
  });
  el.querySelectorAll(".btn-record").forEach((btn) => btn.addEventListener("click", () => startVoRecording(btn)));
  el.querySelectorAll(".btn-stop-record").forEach((btn) => btn.addEventListener("click", () => stopVoRecording(btn)));
}

function isJsonArtifactPath(path) {
  return path.endsWith(".json");
}

function populateArtifactSelect(stage) {
  const sel = $("#artifact-select");
  const paths = [...new Set([...(stage.editable || []), ...(stage.artifacts || [])])].filter(
    (p) => p && !p.endsWith("/") && (isJsonArtifactPath(p) || p.endsWith(".md") || p.endsWith(".txt")),
  );
  sel.innerHTML = paths.map((p) => `<option value="${p}">${p}</option>`).join("");
  if (paths.length) loadSelectedArtifact();
  else {
    $("#artifact-editor").value = "";
    $("#artifact-save-status").textContent = "No editable artifacts for this stage yet.";
  }
}

async function loadSelectedArtifact() {
  const path = $("#artifact-select").value;
  if (!path) return;
  state.artifactIsJson = isJsonArtifactPath(path);
  try {
    const data = await api(`/api/runs/${state.runId}/artifact?path=${encodeURIComponent(path)}`);
    if (state.artifactIsJson) {
      $("#artifact-editor").value = JSON.stringify(data, null, 2);
    } else {
      $("#artifact-editor").value = data.text ?? "";
    }
    $("#artifact-save-status").textContent = `Loaded ${path}`;
  } catch {
    $("#artifact-editor").value = "";
    $("#artifact-save-status").textContent = `${path} not found — run this stage first.`;
  }
}

function themesToText(themes) {
  return (themes || [])
    .map((t) => {
      const id = t.id || "";
      const label = t.label || "";
      const summary = (t.summary || "").replace(/\n/g, " ");
      return `${id} | ${label} | ${summary}`.trim();
    })
    .join("\n");
}

function textToThemes(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, i) => {
      const parts = line.split("|").map((p) => p.trim());
      if (parts.length >= 3) {
        return {
          id: parts[0] || `theme_${i + 1}`,
          label: parts[1],
          summary: parts.slice(2).join(" | "),
          segment_ids: [],
          confidence: 1,
          sources: ["operator"],
        };
      }
      return {
        id: `theme_${i + 1}`,
        label: line,
        summary: "",
        segment_ids: [],
        confidence: 1,
        sources: ["operator"],
      };
    });
}

function questionsToText(questions) {
  return (questions || [])
    .map((q) => (typeof q === "string" ? q : q.question || ""))
    .filter(Boolean)
    .join("\n");
}

function textToQuestions(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((question) => ({ question, segment_ids: [], priority: "medium" }));
}

async function loadAnalysisProfile() {
  if (!state.runId) return;
  try {
    const data = await api(`/api/runs/${state.runId}/analysis-profile`);
    state.analysisProfile = data.analysis_state;
    paintAnalysisProfileForm(data.analysis_state);
    const badge = $("#profile-verified-badge");
    if (data.operator_verified) badge.classList.remove("hidden");
    else badge.classList.add("hidden");
    $("#profile-status").textContent = data.completion?.blockers?.length
      ? `Blockers: ${data.completion.blockers.join("; ")}`
      : "Loaded profile";
  } catch (e) {
    $("#profile-status").textContent = e.message;
  }
}

function paintAnalysisProfileForm(st) {
  if (!st) return;
  const ident = st.interview_identity || {};
  const narrative = st.narrative || {};
  const style = st.style || {};
  $("#profile-title").value = ident.title || "";
  $("#profile-summary").value = ident.one_line_summary || "";
  $("#profile-thesis").value = narrative.thesis || "";
  $("#profile-themes").value = themesToText(st.themes);
  $("#profile-questions").value = questionsToText(st.major_questions);
  $("#profile-tone").value = style.tone || "";
  $("#profile-pacing").value = style.pacing || "";
  $("#profile-int-style").value = style.interviewer_style || "";
  $("#profile-ee-style").value = style.interviewee_style || "";
  $("#profile-notes").value = st.operator_notes || "";
}

function collectAnalysisProfileFromForm() {
  const base = state.analysisProfile || {};
  return {
    ...base,
    interview_identity: {
      ...(base.interview_identity || {}),
      title: $("#profile-title").value.trim(),
      one_line_summary: $("#profile-summary").value.trim(),
    },
    narrative: {
      ...(base.narrative || {}),
      thesis: $("#profile-thesis").value.trim(),
    },
    themes: textToThemes($("#profile-themes").value),
    major_questions: textToQuestions($("#profile-questions").value),
    style: {
      ...(base.style || {}),
      tone: $("#profile-tone").value.trim(),
      pacing: $("#profile-pacing").value.trim(),
      interviewer_style: $("#profile-int-style").value.trim(),
      interviewee_style: $("#profile-ee-style").value.trim(),
    },
    operator_notes: $("#profile-notes").value.trim(),
  };
}

async function saveAnalysisProfile() {
  if (!state.runId) return;
  const data = collectAnalysisProfileFromForm();
  const invalidate = confirm("Save profile? Re-run downstream AI stages if needed.") ? "content_context" : null;
  try {
    await api(`/api/runs/${state.runId}/analysis-profile`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data, invalidate_from: invalidate }),
    });
    showToast("Profile saved");
    await refreshRun();
    await loadAnalysisProfile();
  } catch (e) {
    showToast(e.message);
  }
}

async function verifyAnalysisProfile() {
  if (!state.runId) return;
  const data = collectAnalysisProfileFromForm();
  await api(`/api/runs/${state.runId}/analysis-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data, operator_verified: true }),
  });
  await api(`/api/runs/${state.runId}/analysis-profile/verify`, { method: "POST" });
  showToast("Profile verified");
  await refreshRun();
  await loadAnalysisProfile();
}

async function saveArtifact() {
  const path = $("#artifact-select").value;
  if (!path) return;
  const invalidate = confirm("Save to disk? Downstream stages may need re-run.") ? state.selectedStageId : null;
  if (state.artifactIsJson) {
    let data;
    try {
      data = JSON.parse($("#artifact-editor").value);
    } catch {
      showToast("Invalid JSON");
      return;
    }
    await api(`/api/runs/${state.runId}/artifact`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, data, invalidate_from: invalidate }),
    });
  } else {
    await api(`/api/runs/${state.runId}/artifact/text`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, text: $("#artifact-editor").value, invalidate_from: invalidate }),
    });
  }
  showToast("Saved");
  await refreshRun();
}

function renderTimeline() {
  const track = $("#timeline-track");
  const ruler = $("#timeline-ruler");
  const voTrack = $("#vo-track");
  const meta = $("#timeline-meta");
  const player = $("#audio-player");
  const scroll = $("#timeline-scroll");

  if (!state.timeline?.segments?.length) {
    track.innerHTML = `<p class="empty-state">NLE timeline appears after segment classification.</p>`;
    ruler.innerHTML = "";
    voTrack.innerHTML = "";
    meta.textContent = "";
    player.removeAttribute("src");
    return;
  }

  const { segments, duration_ms, normalized_audio, vo_lines } = state.timeline;
  meta.textContent = `${segments.length} segments · ${formatMs(duration_ms)} · zoom ${state.zoom}x`;

  let banner = $("#nle-rerun-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "nle-rerun-banner";
    meta.after(banner);
  }
  banner.innerHTML = "";
  if (nleHasOperatorEdits(state.nle)) {
    banner.className = "nle-rerun-banner";
    banner.innerHTML = `<p>Timeline edits detected — re-run ranking or rebuild EDL to apply.</p>
      <div class="btn-row">
        <button type="button" class="btn sm primary" data-rerun="full_master_ranking">Re-run ranking</button>
        <button type="button" class="btn sm ghost" data-rerun="edl_flow1">Rebuild EDL</button>
      </div>`;
    banner.querySelectorAll("[data-rerun]").forEach((btn) => {
      btn.onclick = () => executeJob({ mode: "stage", stage: btn.dataset.rerun });
    });
  } else {
    banner.className = "hidden";
  }

  const overrides = state.nle?.segment_overrides || {};

  const audioPath = normalized_audio
    ? `/api/runs/${state.runId}/audio?path=${encodeURIComponent(normalized_audio)}`
    : `/api/runs/${state.runId}/source-audio`;
  if (player.getAttribute("data-src") !== audioPath) {
    player.src = audioPath;
    player.setAttribute("data-src", audioPath);
  }

  const widthPx = Math.max(800, duration_ms / 50) * state.zoom;
  scroll.style.setProperty("--tl-width", `${widthPx}px`);
  track.style.width = `${widthPx}px`;
  ruler.style.width = `${widthPx}px`;

  ruler.innerHTML = "";
  const step = duration_ms > 600000 ? 60000 : 15000;
  for (let t = 0; t <= duration_ms; t += step) {
    const tick = document.createElement("span");
    tick.className = "ruler-tick";
    tick.style.left = `${(t / duration_ms) * 100}%`;
    tick.textContent = formatMs(t);
    ruler.appendChild(tick);
  }

  track.innerHTML = "";
  segments.forEach((seg) => {
    const segId = seg.segment_id || seg._nle_label;
    const left = (seg.start_ms / duration_ms) * 100;
    const width = Math.max(((seg.end_ms - seg.start_ms) / duration_ms) * 100, 0.8);
    const type = seg.type || "";
    const role = seg.speaker_role || "unknown";
    const cls = type === "aside" ? "aside" : role === "interviewer" ? "interviewer" : "interviewee";
    const block = document.createElement("div");
    block.className = `segment-block ${cls}${seg._mark_redo ? " mark-redo" : ""}${seg._excluded ? " excluded nle-excluded" : ""}`;
    block.draggable = true;
    block.dataset.segId = segId;
    block.style.left = `${left}%`;
    block.style.width = `${width}%`;
    const ov = overrides[segId] || overrides[seg.segment_id] || {};
    const splitHint = ov.split_into?.length
      ? ` · split → ${ov.split_into.join(", ")}`
      : ov.split_into
        ? ""
        : "";
    const trimHint =
      ov.start_ms != null && ov.end_ms != null ? ` · trim ${formatMs(ov.start_ms)}–${formatMs(ov.end_ms)}` : "";
    block.title = `${seg.text?.slice(0, 120) || segId}${splitHint}${trimHint}`;
    block.innerHTML = `<div class="seg-label">${segId}</div><div>${formatMs(seg.start_ms)}</div>`;
    block.addEventListener("click", (e) => {
      e.stopPropagation();
      selectSegment(segId, seg.start_ms);
    });
    block.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", segId));
    block.addEventListener("dragover", (e) => e.preventDefault());
    block.addEventListener("drop", (e) => {
      e.preventDefault();
      reorderSegment(e.dataTransfer.getData("text/plain"), segId);
    });
    track.appendChild(block);
  });

  scroll.onclick = (e) => {
    if (e.target.closest(".segment-block")) return;
    const rect = track.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    seekTo(ratio * duration_ms);
  };

  voTrack.innerHTML = "";
  (vo_lines || []).forEach((line) => {
    const seg = segments.find((s) => s.segment_id === line.targets_segment_id);
    if (!seg) return;
    const chip = document.createElement("div");
    chip.className = `vo-chip${line.recorded_file ? " done" : " missing"}`;
    chip.style.left = `${(seg.start_ms / duration_ms) * 100}%`;
    chip.textContent = line.line_id;
    chip.title = line.text;
    voTrack.appendChild(chip);
  });

  updatePlayhead();
}

function selectSegment(segId, startMs) {
  state.selectedSegmentId = segId;
  document.querySelectorAll(".segment-block").forEach((b) => {
    b.classList.toggle("selected", b.dataset.segId === segId);
  });
  seekTo(startMs);
}

function seekTo(ms) {
  state.playheadMs = ms;
  const player = $("#audio-player");
  player.currentTime = ms / 1000;
  updatePlayhead();
}

function updatePlayhead() {
  const duration = state.timeline?.duration_ms || 1;
  const pct = (state.playheadMs / duration) * 100;
  const ph = $("#playhead");
  if (ph) ph.style.left = `${pct}%`;
}

async function patchSelectedSegment(patch) {
  if (!state.selectedSegmentId) {
    showToast("Select a segment on the timeline first.");
    return;
  }
  await api(`/api/runs/${state.runId}/nle/segment`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment_id: state.selectedSegmentId, patch }),
  });
  await refreshRun();
}

async function splitAtPlayhead() {
  if (!state.selectedSegmentId) {
    showToast("Select a segment to split.");
    return;
  }
  await api(`/api/runs/${state.runId}/nle/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment_id: state.selectedSegmentId, at_ms: Math.round(state.playheadMs) }),
  });
  await refreshRun();
}

async function reorderSegment(dragId, targetId) {
  if (!dragId || dragId === targetId) return;
  const order = state.nle?.sequence_order?.length
    ? [...state.nle.sequence_order]
    : (state.timeline?.segments || []).map((s) => s.segment_id);
  const from = order.indexOf(dragId);
  const to = order.indexOf(targetId);
  if (from < 0 || to < 0) return;
  order.splice(from, 1);
  order.splice(to, 0, dragId);
  state.nle = { ...(state.nle || {}), sequence_order: order };
  await saveNle(false);
  await refreshRun();
}

async function saveNle(showMsg = true) {
  const data = {
    ...(state.nle || {}),
    playhead_ms: Math.round(state.playheadMs),
    zoom: state.zoom,
  };
  try {
    await api(`/api/runs/${state.runId}/nle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data }),
    });
    if (showMsg) showToast("Timeline saved");
  } catch (err) {
    const msg = err?.message || "NLE save failed";
    showToast(msg.slice(0, 120));
    throw err;
  }
}

const voRecorder = { media: null, chunks: [] };

async function uploadVoFile(lineId, file) {
  const fd = new FormData();
  fd.append("file", file);
  await fetch(`/api/runs/${state.runId}/vo/${lineId}`, { method: "POST", body: fd });
  const wasMissing = (state.run?.g1_missing || []).length > 0;
  await refreshRun();
  if (wasMissing && state.run?.g1_clear) {
    selectStage("g1_vo_pickup");
  }
}

async function startVoRecording(btn) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    voRecorder.media = new MediaRecorder(stream);
    voRecorder.chunks = [];
    voRecorder.media.ondataavailable = (e) => voRecorder.chunks.push(e.data);
    voRecorder.media.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      await uploadVoFile(btn.dataset.line, new Blob(voRecorder.chunks, { type: "audio/webm" }));
      btn.classList.remove("hidden");
      btn.parentElement.querySelector(".btn-stop-record")?.classList.add("hidden");
    };
    voRecorder.media.start();
    btn.classList.add("hidden");
    btn.parentElement.querySelector(".btn-stop-record")?.classList.remove("hidden");
  } catch {
    showToast("Microphone unavailable");
  }
}

function stopVoRecording() {
  if (voRecorder.media?.state === "recording") voRecorder.media.stop();
}

async function runNextStage() {
  if (hasActionRequiredStage()) {
    const blocked = state.run.stages.find((s) => s.status === "action_required");
    showToast(`Complete checkpoint: ${blocked?.title || "action required"} before running.`);
    if (blocked) selectStage(blocked.id);
    playAttentionPing();
    return;
  }
  const next = findNextRunnableStage();
  if (!next) {
    showToast("No runnable stage — check gates or flow.");
    return;
  }
  if (next.id === "transcript_review" || next.id === "g1_vo_pickup" || next.id === "g2_flow_select") {
    selectStage(next.id);
    return;
  }
  await executeJob({ mode: "stage", stage: next.id });
}

function findNextRunnableStage() {
  for (const s of state.run.stages) {
    if (s.status === "action_required") return s;
    if (s.status === "pending" && s.phase !== "gate") return s;
  }
  return null;
}

async function executeJob(body) {
  if (!(await ensureApiConsentForExecute(body))) {
    showToast("API access not granted — execution cancelled.");
    return;
  }
  const payload = { ...body, api_consents: buildApiConsentsPayload() };
  const res = await api(`/api/runs/${state.runId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok === false) {
    showToast(res.error || "Failed to start");
    if (res.needs_api_consent) await refreshRun();
    return;
  }
  startJobPoll();
}

async function redoFromStage() {
  if (!state.selectedStageId || !confirm(`Redo from “${state.selectedStageId}”?`)) return;
  await api(`/api/runs/${state.runId}/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_stage: mapGateToStage(state.selectedStageId) }),
  });
  await refreshRun();
}

function mapGateToStage(id) {
  if (id === "transcript_review") return "transcript_review_build";
  if (id === "g1_vo_pickup" || id === "g2_flow_select") return "optimal_questions";
  return id;
}

function startJobPoll() {
  stopJobPoll();
  state.jobPoll = setInterval(async () => {
    const job = await api(`/api/runs/${state.runId}/job`);
    updateJobUI(job);
    await pollLog();
    if (job.status !== "running" && job.status !== "running_with_warnings") {
      await refreshRun();
      stopJobPoll();
    }
  }, 1200);
}

function stopJobPoll() {
  if (state.jobPoll) {
    clearInterval(state.jobPoll);
    state.jobPoll = null;
  }
}

function updatePrecleanWarningsBanner(job) {
  const banner = $("#preclean-warnings-banner");
  if (!banner) return;
  const warnings = job?.preclean_warnings;
  if (!Array.isArray(warnings) || !warnings.length) {
    banner.classList.add("hidden");
    banner.textContent = "";
    return;
  }
  const lines = warnings.map(
    (w) =>
      `Pre-clean not acknowledged (${w.checkpoint}) — stage ${w.stage}`,
  );
  banner.textContent = lines.join(" · ");
  banner.classList.remove("hidden");
}

function updateJobUI(job) {
  const running =
    job?.status === "running" || job?.status === "running_with_warnings";
  const blocked = hasActionRequiredStage();
  $("#btn-run-next").disabled = running || blocked;
  $("#btn-run-analysis").disabled = running || blocked;
  updatePrecleanWarningsBanner(job);
  if (
    (job?.status === "gate" || job?.status === "needs_operator") &&
    state.jobStatusPrev !== job?.status
  ) {
    playAttentionPing();
    renderCheckpointBanner();
  }
  state.jobStatusPrev = job?.status ?? null;
  const el = $("#status-job");
  if (job?.status === "running_with_warnings") {
    el.textContent = `Running (warnings) ${job.stage || job.mode}`;
    el.className = "status-value running_with_warnings";
  } else if (running) {
    el.textContent = `Running ${job.stage || job.mode}`;
    el.className = "status-value running";
  } else if (job?.status === "gate" || job?.status === "needs_operator") {
    el.textContent = "Action required";
    el.className = "status-value action";
  } else if (job?.status === "error") {
    el.textContent = "Error";
    el.className = "status-value error";
  } else {
    el.textContent = job?.status === "complete" ? "Complete" : "Idle";
    el.className = "status-value idle";
  }
}

init();
