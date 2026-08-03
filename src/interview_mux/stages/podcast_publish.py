"""Podcast publish stages: meta, cover prompt, MP3, cover art, S3 publish."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from interview_mux.config import repo_root
from interview_mux.gates import require_g_publish_clear
from interview_mux.llm_simple import run_llm_stage_simple
from interview_mux.podcast_rss.catalog import (
    allocate_episode_number,
    apply_version_suffix,
    episode_folder,
    load_by_source_hash,
    prior_publish_count,
    record_execution,
    record_publish,
)
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
from interview_mux.podcast_rss.feed import build_feed_xml, channel_meta_from_config, rfc2822
from interview_mux.podcast_rss.s3_publish import (
    get_json,
    list_episode_metas,
    publish_episode_package,
)
from interview_mux.podcast_rss.settings import (
    episode_prefix,
    podcast_cfg as _podcast_cfg,
    resolve_publish_targets,
    s3_layout,
)
from interview_mux.run_context import RunContext


def _show_artwork_path() -> Path:
    rel = str(_podcast_cfg().get("show_artwork_path") or "config/podcast/the-war-room-cover.png")
    path = repo_root() / rel
    return path


def _copy_show_fallback(ctx: RunContext, dest: Path, *, reason: str) -> Path:
    src = _show_artwork_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, dest)
    else:
        # Minimal 1x1 placeholder should not happen; raise for operator visibility
        raise FileNotFoundError(f"Show artwork missing: {src}")
    ctx.write_json(
        "publish/cover_meta.json",
        {"cover_source": "show_fallback", "reason": reason, "path": str(dest.name)},
    )
    return dest


def _probe_duration_seconds(path: Path) -> int:
    import json as _json
    import shutil as _shutil
    import subprocess

    ffprobe = _shutil.which("ffprobe")
    if not ffprobe or not path.is_file():
        return 0
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    try:
        data = _json.loads(proc.stdout or "{}")
        return int(float((data.get("format") or {}).get("duration") or 0))
    except Exception:
        return 0


def _build_meta_input(ctx: RunContext) -> dict[str, Any]:
    brief = ctx.read_json("understanding/content_brief.json") if ctx.artifact_exists("understanding/content_brief.json") else {}
    narrative = ctx.read_json("master/narrative_plan.json") if ctx.artifact_exists("master/narrative_plan.json") else {}
    selection = ctx.read_json("master/selection.json") if ctx.artifact_exists("master/selection.json") else {}
    return {
        "content_brief": brief if isinstance(brief, dict) else {},
        "narrative_plan": {
            "arc_summary": (narrative or {}).get("arc_summary") if isinstance(narrative, dict) else None,
            "chapters": (narrative or {}).get("chapters") if isinstance(narrative, dict) else [],
        },
        "selection_chapters": (selection or {}).get("chapters") if isinstance(selection, dict) else [],
        "show_title": _podcast_cfg().get("show_title") or "The War Room",
    }


def _persist_meta(ctx: RunContext, artifacts: dict[str, Any]) -> None:
    payload = artifacts if isinstance(artifacts, dict) else {}
    title = str(payload.get("title") or payload.get("title_suggestion") or "").strip()
    description = str(payload.get("description") or payload.get("description_markdown") or "").strip()
    if not title:
        brief = _build_meta_input(ctx).get("content_brief") or {}
        title = str(brief.get("thesis") or "Untitled Episode")[:120]
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
    run_llm_stage_simple(
        ctx,
        "episode_meta_build",
        "publishing/episode-meta.system.txt",
        _build_meta_input,
        _persist_meta,
    )


def _build_cover_prompt_input(ctx: RunContext) -> dict[str, Any]:
    theme = load_cover_theme()
    style_head = refresh_style_head()
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
        # Reject — no silent truncation. Generate stage fail-opens to show art.
        _write_cover_prompt_doc(
            ctx,
            prompt=prompt,
            motifs=motifs,
            without_clauses=without_clauses,
            rejected=True,
            reject_reasons=errors,
            source=source,
            draft_prompt=str(payload.get("draft_prompt") or "") or None,
            brilliance_checklist=payload.get("brilliance_checklist")
            if isinstance(payload.get("brilliance_checklist"), dict)
            else None,
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


def _cover_craft_fallback(ctx: RunContext, *, source: str, reason: str) -> None:
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
    prompt = assemble_prompt(motifs)
    errors = validate_prompt(prompt)
    _write_cover_prompt_doc(
        ctx,
        prompt=prompt,
        motifs=motifs,
        without_clauses=[
            "without photorealism",
            "without readable letters or words in any language",
            "without logos or watermarks",
            "without copying show-art emblems",
        ],
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
        ctx.mark_done(stage_key)
        return
    except Exception as exc:
        ctx.log(f"cover craft finalize failed; harvest fallback: {exc}", level="warning", stage=stage_key)
        _cover_craft_fallback(ctx, source="exception_fallback", reason=str(exc))
        ctx.mark_done(stage_key)


def run_podcast_encode_mp3(ctx: RunContext) -> None:
    master = ctx.path("master/master.wav")
    if not master.is_file():
        raise FileNotFoundError("master/master.wav missing — run master_finalize first")
    bitrate = int(_podcast_cfg().get("mp3_bitrate_k") or 192)
    dest = ctx.path("publish/audio.mp3")
    encode_master_to_mp3(master, dest, bitrate_k=bitrate)
    shutil.copy2(master, ctx.path("publish/master.wav"))
    ctx.log(f"Encoded podcast MP3 ({bitrate}k)", stage="podcast_encode_mp3")
    ctx.mark_done("podcast_encode_mp3")


def _vision_pick_cfg() -> dict[str, Any]:
    cov = _podcast_cfg().get("cover_image") if isinstance(_podcast_cfg().get("cover_image"), dict) else {}
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
    # Also mirror flat 0..2 for stable paths
    flat = ctx.path("publish/cover_candidates")
    flat.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i, src in enumerate(paths):
        dest = flat / f"{i}.png"
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
    dest = ctx.path("publish/cover.png")
    prompt_doc = (
        ctx.read_json("publish/cover_prompt.json")
        if ctx.artifact_exists("publish/cover_prompt.json")
        else {}
    )
    if not isinstance(prompt_doc, dict) or prompt_doc.get("rejected"):
        _copy_show_fallback(ctx, dest, reason="prompt_rejected_or_missing")
        ctx.mark_done("episode_cover_generate")
        return

    prompt = str(prompt_doc.get("prompt") or "").strip()
    if not prompt:
        _copy_show_fallback(ctx, dest, reason="empty_prompt")
        ctx.mark_done("episode_cover_generate")
        return

    from interview_mux.podcast_rss.cover_vision import local_fallback_pick, pick_cover_winner
    from interview_mux.podcast_rss.openai_cover import resolve_cover_image_settings

    settings = resolve_cover_image_settings()
    vp = _vision_pick_cfg()
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
        shutil.copy2(winner_path, dest)
        ctx.write_json(
            "publish/cover_meta.json",
            {
                "cover_source": "openai_generated",
                "path": "cover.png",
                "provider": settings.get("provider") or "openai",
                "model": settings.get("model"),
                "size": settings.get("size"),
                "quality": settings.get("quality"),
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
    require_g_publish_clear(ctx, stage="podcast_publish")
    targets = resolve_publish_targets()
    bucket = targets["bucket"]
    dist_id = targets["distribution_id"]
    base = targets["feed_base_url"]
    region = targets["region"]
    project_name = targets["project_name"]
    if not bucket or not dist_id or not base:
        raise RuntimeError(
            "Missing podcast.s3_bucket (app.defaults) and/or "
            "PODCAST_CLOUDFRONT_DISTRIBUTION_ID / PODCAST_FEED_BASE_URL (secrets.env)"
        )

    layout = s3_layout()
    files = layout["episode_files"]
    catalog_prefix = layout["catalog_prefix"]

    meta = ctx.read_json("publish/episode_meta.json") if ctx.artifact_exists("publish/episode_meta.json") else {}
    run_meta = ctx.read_json("run_meta.json") if ctx.artifact_exists("run_meta.json") else {}
    source_hash = str((run_meta or {}).get("source_audio_hash") or "")
    execution_id = str((run_meta or {}).get("execution_id") or ctx.run_id)

    sequence = get_json(bucket, f"{catalog_prefix}/sequence.json", region=region) or {
        "next_episode_number": 1
    }
    by_hash_raw = get_json(bucket, f"{catalog_prefix}/by_source_hash.json", region=region) or {}
    by_exec_raw = get_json(bucket, f"{catalog_prefix}/by_execution_id.json", region=region) or {}
    by_hash = load_by_source_hash(by_hash_raw)
    prior = prior_publish_count(by_hash, source_hash) if source_hash else 0
    base_title = str((meta or {}).get("title") or "Untitled Episode")
    title = apply_version_suffix(base_title, prior_count=prior)
    episode_number, sequence = allocate_episode_number(sequence)
    folder = episode_folder(episode_number)
    prefix = episode_prefix(episode_number)

    mp3 = ctx.path(f"publish/{files['audio']}")
    cover = ctx.path(f"publish/{files['cover']}")
    if not mp3.is_file():
        # Legacy local name during transition
        mp3 = ctx.path("publish/audio.mp3")
    if not mp3.is_file():
        raise FileNotFoundError(f"publish/{files['audio']} missing")
    if not cover.is_file():
        cover = ctx.path("publish/cover.png")
    if not cover.is_file():
        _copy_show_fallback(ctx, cover, reason="missing_at_publish")

    duration = _probe_duration_seconds(mp3)
    published_at = datetime.now(timezone.utc).isoformat()
    description = str((meta or {}).get("description") or title)
    enclosure_url = f"{base}/{prefix}/{files['audio']}"
    cover_url = f"{base}/{prefix}/{files['cover']}"
    description_url = f"{base}/{prefix}/{files['description']}"
    episode_doc = {
        "episode_number": episode_number,
        "title": title,
        "description": description,
        "guid": execution_id,
        "execution_id": execution_id,
        "source_audio_hash": source_hash,
        "s3_prefix": prefix,
        "pub_date": rfc2822(),
        "published_at": published_at,
        "enclosure_url": enclosure_url,
        "enclosure_length": mp3.stat().st_size,
        "duration_seconds": duration,
        "cover_url": cover_url,
        "description_url": description_url,
        "cover_source": (
            (ctx.read_json("publish/cover_meta.json") or {}).get("cover_source")
            if ctx.artifact_exists("publish/cover_meta.json")
            else "unknown"
        ),
    }
    ctx.write_json(f"publish/{files['meta']}", episode_doc)
    ctx.path(f"publish/{files['description']}").write_text(description + "\n", encoding="utf-8")

    # chapters optional
    if ctx.artifact_exists("master/selection.json"):
        sel = ctx.read_json("master/selection.json")
        chapters = (sel or {}).get("chapters") if isinstance(sel, dict) else []
        if chapters:
            ctx.write_json(f"publish/{files['chapters']}", {"chapters": chapters})

    by_hash = record_publish(
        by_hash,
        source_audio_hash=source_hash or execution_id,
        episode_number=episode_number,
        title=title,
        execution_id=execution_id,
        published_at=published_at,
        s3_prefix=prefix,
    )
    by_execution = record_execution(
        by_exec_raw if isinstance(by_exec_raw, dict) else {},
        execution_id=execution_id,
        episode_number=episode_number,
        title=title,
        source_audio_hash=source_hash,
        published_at=published_at,
        s3_prefix=prefix,
    )

    channel = channel_meta_from_config(_podcast_cfg())
    existing = list_episode_metas(bucket, region=region)
    existing = [e for e in existing if str(e.get("guid")) != execution_id]
    feed_episodes = [episode_doc] + existing
    feed_xml = build_feed_xml(
        channel=channel,
        feed_url=f"{base}/{layout['feed_key']}",
        show_artwork_url=f"{base}/{layout['show_prefix']}/artwork.png",
        episodes=feed_episodes,
    )
    ctx.path("publish/feed.xml").write_text(feed_xml, encoding="utf-8")

    result = publish_episode_package(
        bucket=bucket,
        feed_base_url=base,
        distribution_id=dist_id,
        episode_number=episode_number,
        local_dir=ctx.path("publish"),
        episode_meta=episode_doc,
        feed_xml=feed_xml,
        sequence=sequence,
        by_source_hash=by_hash,
        by_execution_id=by_execution,
        show_artwork=_show_artwork_path(),
        region=region,
        project_name=project_name,
    )
    ctx.write_json("publish/publish_result.json", result)
    ctx.log(
        f"Published episode {folder}: {result.get('enclosure_url')}",
        stage="podcast_publish",
    )
    ctx.mark_done("podcast_publish")


def run_podcast_publish_skip(ctx: RunContext) -> None:
    """Mark publish skipped without uploading."""
    from interview_mux.gates import clear_g_publish

    clear_g_publish(ctx, skipped=True)
    ctx.write_json("publish/publish_result.json", {"skipped": True})
    ctx.mark_done("podcast_publish")
