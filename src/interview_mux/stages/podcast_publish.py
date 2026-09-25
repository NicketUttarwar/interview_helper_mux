"""Podcast publish stages: meta, cover prompt, MP3, cover art, local package finalize.

S3 / RSS upload is a separate sync scoped to the current execution
(``podcast_rss.sync_assets`` / ``scripts/sync_podcast_episodes.py --execution-id``),
not part of the per-run pipeline.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from interview_mux.llm_simple import run_llm_stage_simple
from interview_mux.podcast_rss.cover_prompt import (
    BRILLIANT_EXEMPLAR,
    DISAMBIGUATION_VOLLEY,
    STYLE_CONTRACT_VERSION,
    assemble_prompt,
    build_style_head,
    estimate_tokens,
    harvest_motif_context,
    load_cover_theme,
    prompt_max_chars,
    refresh_style_head,
    validate_prompt,
)
from interview_mux.stages.llm_runner import run_prompt_envelope
from interview_mux.podcast_rss.encode import encode_master_to_mp3
from interview_mux.podcast_rss.settings import (
    podcast_id_from_ctx,
    s3_layout,
    show_artwork_source_rel,
    show_cfg,
)
from interview_mux.run_context import RunContext


def _podcast_cfg(ctx: RunContext | None = None) -> dict[str, Any]:
    if ctx is None:
        return show_cfg()
    return show_cfg(podcast_id_from_ctx(ctx))


def _show_artwork_path(ctx: RunContext | None = None) -> Path:
    from interview_mux.config import repo_root

    return repo_root() / show_artwork_source_rel(_podcast_cfg(ctx))


def _copy_show_fallback(ctx: RunContext, dest: Path, *, reason: str) -> Path:
    from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings

    src = _show_artwork_path(ctx)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not src.is_file():
        raise FileNotFoundError(f"Show artwork missing: {src}")
    settings = resolve_cover_image_settings(_podcast_cfg(ctx))
    ensure_square_cover(
        src,
        min_size=int(settings.get("min_output_px") or 3000),
        output_format=str(settings.get("output_format") or "jpeg"),
        jpeg_quality=int(settings.get("jpeg_quality") or 90),
        dest=dest,
    )
    ctx.write_json(
        "publish/cover_meta.json",
        {"cover_source": "show_fallback", "reason": reason, "path": str(dest.name)},
    )
    return dest


def _build_meta_input(ctx: RunContext) -> dict[str, Any]:
    # Contract hard: selection (EMB-B2). Caller must refuse before LLM when absent.
    if not ctx.artifact_exists("master/selection.json"):
        raise RuntimeError("selection required before episode_meta_build")
    brief = ctx.read_json("understanding/content_brief.json") if ctx.artifact_exists("understanding/content_brief.json") else {}
    narrative = ctx.read_json("master/narrative_plan.json") if ctx.artifact_exists("master/narrative_plan.json") else {}
    selection = ctx.read_json("master/selection.json")
    return {
        "content_brief": brief if isinstance(brief, dict) else {},
        "narrative_plan": {
            "arc_summary": (narrative or {}).get("arc_summary") if isinstance(narrative, dict) else None,
            "chapters": (narrative or {}).get("chapters") if isinstance(narrative, dict) else [],
        },
        "selection_chapters": (selection or {}).get("chapters") if isinstance(selection, dict) else [],
        "show_title": _podcast_cfg(ctx).get("show_title") or "Zero Shot Podcast DEMO",
    }


def _is_placeholder_episode_title(title: str) -> bool:
    """True for empty or Untitled* placeholders (EMB-B1)."""
    cleaned = str(title or "").strip()
    if not cleaned:
        return True
    low = cleaned.casefold()
    if low in {"untitled", "untitled episode"}:
        return True
    return low.startswith("untitled ")


def _persist_meta(ctx: RunContext, artifacts: dict[str, Any]) -> None:
    payload = artifacts if isinstance(artifacts, dict) else {}
    title = str(payload.get("title") or payload.get("title_suggestion") or "").strip()
    description = str(payload.get("description") or payload.get("description_markdown") or "").strip()
    if not title:
        brief = _build_meta_input(ctx).get("content_brief") or {}
        title = str(brief.get("thesis") or "").strip()[:120]
    # EMB-B1: refuse empty/Untitled — stage stays incomplete (no hollow done).
    if _is_placeholder_episode_title(title):
        raise RuntimeError(
            "episode_meta_build incomplete: non-empty real title required "
            "(refusing empty/Untitled)"
        )
    if not description:
        description = title
    ctx.write_json(
        "publish/episode_meta.json",
        {
            "title": title,
            "description": description,
            "word_count": len(description.split()),
        },
    )


def run_episode_meta_build(ctx: RunContext) -> None:
    # EMB-B2: match contract hard selection before any OpenAI call.
    if not ctx.artifact_exists("master/selection.json"):
        raise RuntimeError("selection required before episode_meta_build")
    run_llm_stage_simple(
        ctx,
        "episode_meta_build",
        "publishing/episode-meta.system.txt",
        _build_meta_input,
        _persist_meta,
    )


def _build_cover_prompt_input(ctx: RunContext) -> dict[str, Any]:
    theme = load_cover_theme(_podcast_cfg(ctx))
    style_head = refresh_style_head(_podcast_cfg(ctx))
    harvest = harvest_motif_context(ctx)
    max_chars = prompt_max_chars()
    return {
        "harvest": harvest,
        "style_head": style_head,
        "style_contract_version": STYLE_CONTRACT_VERSION,
        "theme_version": theme.get("version"),
        "required_accents": theme.get("required_accents") or ["cerulean", "crimson"],
        "prompt_max_chars": max_chars,
        "prompt_max_tokens": max(32, max_chars // 4),
        "brilliant_exemplar": BRILLIANT_EXEMPLAR,
        "disambiguation": DISAMBIGUATION_VOLLEY,
        "instructions": (
            "Draft then finalize one rich positive image prompt with full anatomy. "
            "Asterisks-only depicted text. Without-clauses only (no negative_prompt). "
            "Never truncate; if over budget, rewrite tighter while keeping anatomy."
        ),
    }


def _write_cover_prompt_doc(
    ctx: RunContext,
    *,
    prompt: str,
    motifs: list[str],
    without_clauses: list[str],
    rejected: bool,
    reject_reasons: list[str] | None = None,
    source: str = "llm",
    draft_prompt: str | None = None,
    brilliance_checklist: dict[str, Any] | None = None,
) -> None:
    max_chars = prompt_max_chars()
    ctx.write_json(
        "publish/cover_prompt.json",
        {
            "prompt": prompt,
            "draft_prompt": draft_prompt,
            "motifs": motifs,
            "without_clauses": without_clauses,
            "negative_prompt": "",
            "token_estimate": estimate_tokens(prompt),
            "prompt_max_chars": max_chars,
            "prompt_max_tokens": max_chars // 4,
            "style_contract_version": STYLE_CONTRACT_VERSION,
            "style_head": build_style_head(),
            "brilliance_checklist": brilliance_checklist or {},
            "rejected": rejected,
            "reject_reasons": list(reject_reasons or []),
            "source": source,
        },
    )


def _persist_cover_artifacts(ctx: RunContext, artifacts: dict[str, Any], *, source: str = "llm") -> None:
    payload = artifacts if isinstance(artifacts, dict) else {}
    motifs_raw = payload.get("motifs") or []
    motifs = [str(m).strip() for m in motifs_raw if str(m).strip()][:6]
    without_raw = payload.get("without_clauses") or []
    without_clauses = [str(w).strip() for w in without_raw if str(w).strip()]
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        prompt = assemble_prompt(motifs, without_clauses=without_clauses or None)
    errors = validate_prompt(prompt)
    if errors:
        # F7 2B: no silent truncation — harvest a valid backup and still generate.
        ctx.log(
            "cover craft LLM prompt rejected; harvest fallback: " + ";".join(errors),
            level="warning",
            stage="episode_cover_prompt_craft",
        )
        _cover_craft_fallback(
            ctx,
            source="harvest_after_reject",
            reason=";".join(errors),
        )
        return
    _write_cover_prompt_doc(
        ctx,
        prompt=prompt,
        motifs=motifs,
        without_clauses=without_clauses,
        rejected=False,
        source=source,
        draft_prompt=str(payload.get("draft_prompt") or "") or None,
        brilliance_checklist=payload.get("brilliance_checklist")
        if isinstance(payload.get("brilliance_checklist"), dict)
        else None,
    )


def _harvest_cover_motifs(ctx: RunContext) -> list[str]:
    harvest = harvest_motif_context(ctx)
    motifs: list[str] = []
    for key in ("thesis", "episode_title", "sonic_mood"):
        val = harvest.get(key)
        if val:
            motifs.append(str(val)[:80])
    for t in harvest.get("themes") or []:
        motifs.append(str(t)[:60])
        if len(motifs) >= 4:
            break
    if not motifs:
        motifs = ["abstract geometric focal emblem", "interlocking arcs"]
    return motifs


def _harvest_cover_prompt(ctx: RunContext) -> tuple[str, list[str], list[str]]:
    motifs = _harvest_cover_motifs(ctx)
    prompt = assemble_prompt(motifs)
    return prompt, motifs, validate_prompt(prompt)


def _cover_craft_fallback(ctx: RunContext, *, source: str, reason: str) -> None:
    prompt, motifs, errors = _harvest_cover_prompt(ctx)
    _write_cover_prompt_doc(
        ctx,
        prompt=prompt,
        motifs=motifs,
        without_clauses=[],
        rejected=bool(errors),
        reject_reasons=errors or [reason],
        source=source,
    )


def run_episode_cover_prompt_craft(ctx: RunContext) -> None:
    """Flagship draft → finalize volley (max 2 chat attempts). No silent truncation."""
    stage_key = "episode_cover_prompt_craft"
    prompt_rel = "publishing/episode-cover-prompt.system.txt"
    base_input = _build_cover_prompt_input(ctx)
    user_payload = json.dumps(base_input, indent=2, ensure_ascii=False)

    draft_artifacts: dict[str, Any] | None = None
    try:
        draft_env = run_prompt_envelope(
            stage_key,
            prompt_rel,
            user_payload
            + "\n\n---\nDRAFT PASS: invent motifs from harvest and produce draft_prompt + motifs. "
            "You may leave prompt as the draft; finalize pass will polish.",
            ctx=ctx,
            call_attempt=1,
            messages=[{"role": "user", "content": user_payload + "\n\nDRAFT PASS."}],
            include_preamble=False,
        )
        if isinstance(draft_env.get("artifacts"), dict):
            draft_artifacts = draft_env["artifacts"]
    except Exception as exc:
        ctx.log(f"cover craft draft failed: {exc}", level="warning", stage=stage_key)
        draft_artifacts = None

    try:
        finalize_user = {
            "base": base_input,
            "draft_artifacts": draft_artifacts or {},
            "brilliance_checklist_required": True,
            "instructions": (
                "FINALIZE PASS: produce the full `prompt` with complete anatomy and without-clauses. "
                "Apply brilliance checklist. Do not truncate; rewrite if over prompt_max_chars."
            ),
        }
        final_env = run_prompt_envelope(
            stage_key,
            prompt_rel,
            json.dumps(finalize_user, indent=2, ensure_ascii=False),
            ctx=ctx,
            call_attempt=2,
            messages=[
                {"role": "user", "content": user_payload + "\n\nDRAFT PASS."},
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"status": "complete", "artifacts": draft_artifacts or {}},
                        ensure_ascii=False,
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(finalize_user, indent=2, ensure_ascii=False),
                },
            ],
            include_preamble=False,
        )
        arts = final_env.get("artifacts") if isinstance(final_env.get("artifacts"), dict) else {}
        if draft_artifacts and not arts.get("draft_prompt"):
            arts = {
                **arts,
                "draft_prompt": str(
                    draft_artifacts.get("draft_prompt")
                    or draft_artifacts.get("prompt")
                    or ""
                )
                or None,
            }
        _persist_cover_artifacts(ctx, arts, source="llm_volley")
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, stage_key)
        return
    except Exception as exc:
        ctx.log(f"cover craft finalize failed; harvest fallback: {exc}", level="warning", stage=stage_key)
        _cover_craft_fallback(ctx, source="exception_fallback", reason=str(exc))
        from interview_mux.stage_completion import heal_or_raise

        heal_or_raise(ctx, stage_key)


def run_podcast_encode_mp3(ctx: RunContext) -> None:
    from interview_mux.post_master_quality import require_publishable

    require_publishable(ctx, stage="podcast_encode_mp3")
    # Read upstream master from final/prior path — ctx.path() is the active
    # staging root and would miss master/master.wav written by master_finalize.
    master = ctx.read_path("master/master.wav")
    if not master.is_file():
        raise FileNotFoundError("master/master.wav missing — run master_finalize first")
    bitrate = int(_podcast_cfg(ctx).get("mp3_bitrate_k") or 192)
    channels = int(_podcast_cfg(ctx).get("mp3_channels") or 2)
    dest = ctx.path("publish/audio.mp3")
    encode_master_to_mp3(master, dest, bitrate_k=bitrate, channels=channels)
    shutil.copy2(master, ctx.path("publish/master.wav"))
    ctx.log(
        f"Encoded podcast MP3 ({bitrate}k, {channels}ch)",
        stage="podcast_encode_mp3",
    )
    from interview_mux.stage_completion import heal_or_raise

    heal_or_raise(ctx, "podcast_encode_mp3")


def _vision_pick_cfg(ctx: RunContext | None = None) -> dict[str, Any]:
    cov = _podcast_cfg(ctx).get("cover_image") if isinstance(_podcast_cfg(ctx).get("cover_image"), dict) else {}
    vp = cov.get("vision_pick") if isinstance(cov.get("vision_pick"), dict) else {}
    return {
        "enabled": vp.get("enabled", True),
        "max_rebatch": int(vp.get("max_rebatch") if vp.get("max_rebatch") is not None else 1),
        "on_final_fail": str(vp.get("on_final_fail") or "show_fallback"),
        "primary_criterion": str(vp.get("primary_criterion") or "brilliance"),
    }


def _run_cover_candidate_batch(
    ctx: RunContext,
    *,
    prompt: str,
    settings: dict[str, Any],
    batch_index: int,
) -> list[Path]:
    from interview_mux.podcast_rss.openai_cover import generate_cover_candidates

    dest_dir = ctx.path(f"publish/cover_candidates/batch_{batch_index}")
    if dest_dir.is_dir():
        shutil.rmtree(dest_dir)
    paths = generate_cover_candidates(prompt=prompt, dest_dir=dest_dir, settings=settings)
    # Also mirror flat 0..n for stable paths
    flat = ctx.path("publish/cover_candidates")
    flat.mkdir(parents=True, exist_ok=True)
    out_ext = ".jpg" if str(settings.get("output_format") or "jpeg").lower() in {"jpg", "jpeg"} else ".png"
    out: list[Path] = []
    for i, src in enumerate(paths):
        dest = flat / f"{i}{out_ext}"
        shutil.copy2(src, dest)
        out.append(dest)
    return out


def _all_hard_failed(pick: dict[str, Any], candidate_count: int) -> bool:
    if pick.get("all_hard_failed"):
        return True
    dq = pick.get("disqualified") or []
    hard_idxs = set()
    for d in dq:
        if not isinstance(d, dict):
            continue
        reasons = " ".join(str(r).lower() for r in (d.get("reasons") or []))
        if any(k in reasons for k in ("letter", "text", "word", "photo", "broken", "empty")):
            try:
                hard_idxs.add(int(d["index"]))
            except (KeyError, TypeError, ValueError):
                continue
    return len(hard_idxs) >= candidate_count


def run_episode_cover_generate(ctx: RunContext) -> None:
    """OpenAI ×3 candidates + flagship vision pick (brilliance primary); fail-open show art."""
    files = s3_layout(_podcast_cfg(ctx)).get("episode_files") or {}
    cover_name = str(files.get("cover") or "cover.jpg")
    dest = ctx.path(f"publish/{cover_name}")
    prompt_doc = (
        ctx.read_json("publish/cover_prompt.json")
        if ctx.artifact_exists("publish/cover_prompt.json")
        else {}
    )
    prompt = str(prompt_doc.get("prompt") or "").strip() if isinstance(prompt_doc, dict) else ""
    rejected = bool(isinstance(prompt_doc, dict) and prompt_doc.get("rejected"))
    # F7 2B: rejected/empty craft → harvest backup, then still try OpenAI generate.
    if rejected or not prompt:
        harvest, motifs, herr = _harvest_cover_prompt(ctx)
        if herr or not harvest:
            _copy_show_fallback(
                ctx,
                dest,
                reason="harvest_prompt_invalid:" + ",".join(herr[:4]),
            )
            ctx.mark_done("episode_cover_generate")
            return
        _write_cover_prompt_doc(
            ctx,
            prompt=harvest,
            motifs=motifs,
            without_clauses=[],
            rejected=False,
            reject_reasons=["prompt_rejected_or_missing"] if rejected else ["empty_prompt"],
            source="harvest_generate_retry",
        )
        prompt = harvest

    from interview_mux.podcast_rss.cover_vision import local_fallback_pick, pick_cover_winner
    from interview_mux.podcast_rss.openai_cover import (
        ensure_square_cover,
        require_cover_min_size,
        resolve_cover_image_settings,
    )

    settings = resolve_cover_image_settings(_podcast_cfg(ctx))
    vp = _vision_pick_cfg(ctx)
    meta = ctx.read_json("publish/episode_meta.json") if ctx.artifact_exists("publish/episode_meta.json") else {}
    harvest = harvest_motif_context(ctx)
    max_rebatch = max(0, int(vp.get("max_rebatch") or 0))

    try:
        pick: dict[str, Any] | None = None
        paths: list[Path] = []
        for batch in range(max_rebatch + 1):
            batch_prompt = prompt
            if batch > 0:
                batch_prompt = (
                    prompt
                    + " Micro-revision: strengthen without readable letters or words; "
                    "keep asterisks-only plates; heighten brilliance and accent clarity."
                )
            paths = _run_cover_candidate_batch(
                ctx, prompt=batch_prompt, settings=settings, batch_index=batch
            )
            if not paths:
                raise RuntimeError("no cover candidates generated")
            try:
                if vp.get("enabled", True):
                    pick = pick_cover_winner(
                        candidate_paths=paths,
                        episode_title=(meta or {}).get("title") if isinstance(meta, dict) else None,
                        thesis=harvest.get("thesis"),
                    )
                else:
                    pick = local_fallback_pick(paths)
            except Exception as exc:
                ctx.log(f"vision pick failed: {exc}", level="warning", stage="episode_cover_generate")
                pick = local_fallback_pick(paths)

            ctx.write_json(
                "publish/cover_pick.json",
                {**pick, "batch_index": batch, "prompt_used": batch_prompt[:2000]},
            )
            if not _all_hard_failed(pick, len(paths)):
                break
            if batch >= max_rebatch:
                break
            ctx.log(
                "All candidates hard-failed; re-batching once",
                level="warning",
                stage="episode_cover_generate",
            )

        assert pick is not None
        if _all_hard_failed(pick, len(paths)) and vp.get("on_final_fail") == "show_fallback":
            _copy_show_fallback(ctx, dest, reason="all_candidates_hard_failed")
            ctx.mark_done("episode_cover_generate")
            return

        winner_i = int(pick["winner_index"])
        winner_path = paths[winner_i]
        ensure_square_cover(
            winner_path,
            min_size=int(settings.get("min_output_px") or 3000),
            output_format=str(settings.get("output_format") or "jpeg"),
            jpeg_quality=int(settings.get("jpeg_quality") or 90),
            dest=dest,
        )
        # ECG-B3: Apple 1400×1400 floor at generate (not only podcast_publish).
        require_cover_min_size(dest, min_px=1400)
        # Mirror into the committed tree so encode/publish invalidation cannot
        # lose the only copy that lived under .pending_writes/.
        final_cover = ctx.final_path("publish", cover_name)
        if dest.is_file() and dest.resolve() != final_cover.resolve():
            final_cover.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, final_cover)
        ctx.write_json(
            "publish/cover_meta.json",
            {
                "cover_source": "openai_generated",
                "path": cover_name,
                "provider": settings.get("provider") or "openai",
                "model": settings.get("model"),
                "size": settings.get("size"),
                "quality": settings.get("quality"),
                "min_output_px": settings.get("min_output_px"),
                "output_format": settings.get("output_format") or "jpeg",
                "candidate_count": len(paths),
                "winner_index": winner_i,
                "pick_model": pick.get("pick_model"),
                "primary_criterion": vp.get("primary_criterion") or "brilliance",
                "style_contract_version": STYLE_CONTRACT_VERSION,
            },
        )
    except Exception as exc:
        ctx.log(f"Cover generate failed-open: {exc}", level="warning", stage="episode_cover_generate")
        _copy_show_fallback(ctx, dest, reason=str(exc))
    ctx.mark_done("episode_cover_generate")


def run_podcast_publish(ctx: RunContext) -> None:
    """Finalize a local episode package under publish/ — no S3 upload.

    Upload is a separate sync for this execution only (GUI G-Publish sync or
    ``scripts/sync_podcast_episodes.py --execution-id``).

    Refuse→assemble→stamp only: missing cover / master VTT / PMQ refuse
    upstream — this stage does not nested-build transcript, show-fallback
    cover, or soft-heal PMQ. ``require_g_publish_clear`` stays dead (clinic
    B4 / HPUB); Partial G-Publish is GUI wait, not a stage body gate.
    """
    from datetime import datetime, timezone

    from interview_mux.post_master_quality import require_publishable
    from interview_mux.podcast_rss.chapters import build_timed_chapters
    from interview_mux.podcast_rss.openai_cover import require_cover_min_size

    require_publishable(ctx, stage="podcast_publish")
    layout = s3_layout(_podcast_cfg(ctx))
    files = layout["episode_files"]

    def _existing_publish(rel: str) -> Path:
        """Resolve a publish/ file for read: staging write if present, else prior final."""
        staged = ctx.path(rel)
        if staged.is_file() and staged.stat().st_size > 0:
            return staged
        return ctx.read_path(rel)

    # Cover must already exist (episode_cover_generate). Legacy cover.png → jpg
    # is materialize-only; never show-fallback / cover_meta unpaid land here.
    cover_rel = f"publish/{files['cover']}"
    cover = ctx.path(cover_rel)
    if not cover.is_file():
        legacy = _existing_publish("publish/cover.png")
        if legacy.is_file():
            from interview_mux.podcast_rss.openai_cover import ensure_square_cover, resolve_cover_image_settings

            settings = resolve_cover_image_settings(_podcast_cfg(ctx))
            ensure_square_cover(
                legacy,
                min_size=int(settings.get("min_output_px") or 3000),
                output_format="jpeg",
                jpeg_quality=int(settings.get("jpeg_quality") or 90),
                dest=cover,
            )
        else:
            prior = _existing_publish(cover_rel)
            if prior.is_file() and prior.resolve() != cover.resolve():
                cover.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(prior, cover)
            else:
                raise FileNotFoundError(
                    f"{cover_rel} missing — resume episode_cover_generate "
                    "(podcast_publish does not invent show-fallback art)"
                )

    chapters_doc = build_timed_chapters(ctx)
    ctx.write_json(f"publish/{files['chapters']}", chapters_doc)

    transcript_name = str(files.get("transcript") or "transcript.vtt")
    transcript_rel = f"publish/{transcript_name}"
    transcript_dest = ctx.path(transcript_rel)
    transcript_dest.parent.mkdir(parents=True, exist_ok=True)
    if not ctx.artifact_exists("master/transcript.vtt"):
        raise FileNotFoundError(
            "master/transcript.vtt missing — resume master_transcript_build "
            "(podcast_publish does not nested-build the master VTT)"
        )
    master_vtt = ctx.read_path("master/transcript.vtt")
    if not master_vtt.is_file() or master_vtt.stat().st_size < 1:
        raise FileNotFoundError("master/transcript.vtt missing — cannot package Apple transcript")
    from interview_mux.asset_transcripts import require_packagable_master_transcript

    require_packagable_master_transcript(ctx)
    shutil.copy2(master_vtt, transcript_dest)
    master_pub = ctx.path(f"publish/{files['master']}")
    if not master_pub.is_file():
        # Prefer encode's publish/master.wav copy; else master/master.wav.
        prior = _existing_publish(f"publish/{files['master']}")
        if prior.is_file() and prior.resolve() != master_pub.resolve():
            shutil.copy2(prior, master_pub)
        else:
            master_src = ctx.read_path("master/master.wav")
            if not master_src.is_file():
                raise FileNotFoundError("master/master.wav missing — cannot package archive copy")
            shutil.copy2(master_src, master_pub)

    require_cover_min_size(cover, min_px=1400)

    for key in ("audio", "master", "cover", "chapters", "transcript"):
        rel = f"publish/{files[key]}"
        path = _existing_publish(rel)
        if not path.is_file() or path.stat().st_size < 1:
            raise FileNotFoundError(f"{rel} missing or empty — cannot finalize package")
        # Materialize upstream files into this stage's staging so commit is complete.
        staged = ctx.path(rel)
        if path.resolve() != staged.resolve():
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, staged)

    meta = ctx.read_json("publish/episode_meta.json") if ctx.artifact_exists("publish/episode_meta.json") else {}
    run_meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    source_hash = str((run_meta or {}).get("source_audio_hash") or "")
    execution_id = str((run_meta or {}).get("execution_id") or ctx.run_id)
    season = int(_podcast_cfg(ctx).get("season") or 1)
    title = str((meta or {}).get("title") or "Untitled Episode").strip() or "Untitled Episode"
    description = str((meta or {}).get("description") or title).strip() or title
    prepared_at = datetime.now(timezone.utc).isoformat()

    episode_draft = {
        "season": season,
        "title": title,
        "description": description,
        "guid": execution_id,
        "execution_id": execution_id,
        "podcast_id": podcast_id_from_ctx(ctx),
        "source_audio_hash": source_hash,
        "prepared_at": prepared_at,
        "package_status": "ready_local",
        "cover_source": (
            (ctx.read_json("publish/cover_meta.json") or {}).get("cover_source")
            if ctx.artifact_exists("publish/cover_meta.json")
            else "unknown"
        ),
    }
    ctx.write_json(f"publish/{files['meta']}", episode_draft)
    ctx.path(f"publish/{files['description']}").write_text(description + "\n", encoding="utf-8")
    ctx.write_json(
        "publish/package_ready.json",
        {
            "ready": True,
            "prepared_at": prepared_at,
            "execution_id": execution_id,
            "title": title,
            "files": {
                "audio": files["audio"],
                "master": files["master"],
                "cover": files["cover"],
                "chapters": files["chapters"],
                "transcript": files.get("transcript") or "transcript.vtt",
                "meta": files["meta"],
                "description": files["description"],
            },
        },
    )
    ctx.write_json(
        "publish/publish_result.json",
        {
            "local_package": True,
            "uploaded": False,
            "execution_id": execution_id,
            "title": title,
            "prepared_at": prepared_at,
            "hint": "G-Publish → Upload this run to S3 (or scripts/sync_podcast_episodes.py --execution-id …)",
        },
    )
    ctx.log(
        f"Local episode package ready for {execution_id} — sync separately to upload",
        stage="podcast_publish",
    )
    ctx.mark_done("podcast_publish")


def run_podcast_publish_skip(ctx: RunContext) -> None:
    """Mark publish skipped without packaging or uploading.

    Clinic B1 / HPUB-2: write ``package_ready`` with ``ready:false`` +
    ``skipped:true`` so seed-complete is honest (not hollow mark_done alone).
    """
    from interview_mux.gates import clear_g_publish

    clear_g_publish(ctx, skipped=True)
    ctx.write_json(
        "publish/package_ready.json",
        {"ready": False, "skipped": True},
    )
    ctx.write_json("publish/publish_result.json", {"skipped": True})
    ctx.mark_done("podcast_publish")
