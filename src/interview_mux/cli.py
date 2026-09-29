from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from interview_mux.gates import check_g1_vo
from interview_mux.pipeline import run_analysis, run_delivery
from interview_mux.config import merged_config, repo_root
from interview_mux.run_context import EXEC_ID_RE, LEGACY_RUN_RE, RunContext
from interview_mux.run_lock import run_directory_lock
from interview_mux.write_staging import check_write_approval_before_execute
from interview_mux.source_audio_hash import pipeline_wav_path, source_audio_hash_pair
from interview_mux.stage_execution_reuse import configure_stage_reuse_cli

app = typer.Typer(help="interview_helper_mux pipeline")
console = Console()


def _emit(
    ctx: RunContext | None,
    message: str,
    *,
    level: str = "info",
    stage: str | None = None,
    console_markup: str | None = None,
) -> None:
    """Write operator-visible output to gui_log.jsonl when a run exists, and to the terminal."""
    if ctx is not None:
        ctx.log(message, level=level, stage=stage or "cli")
    console.print(console_markup or message)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    run_id: str | None = typer.Option(None, "--run-id"),
    analysis_only: bool = typer.Option(False, "--analysis-only", help="Stop after analysis"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="Skip if analysis_complete.json exists"),
    from_stage: str | None = typer.Option(None, "--from-stage", help="Analysis stage to restart from"),
    delivery_from_stage: str | None = typer.Option(None, "--delivery-from-stage", help="Delivery stage to restart from"),
) -> None:
    """Default: run analysis, then delivery (unless --analysis-only)."""
    if ctx.invoked_subcommand is not None:
        return
    run_pipeline(
        run_id=run_id,
        analysis_only=analysis_only,
        skip_analysis=skip_analysis,
        from_stage=from_stage,
        delivery_from_stage=delivery_from_stage,
    )
    raise typer.Exit()


def _open_run(run_id: str | None) -> RunContext:
    if run_id:
        if not (EXEC_ID_RE.match(run_id) or LEGACY_RUN_RE.match(run_id)):
            console.print(f"[red]Invalid --run-id:[/red] {run_id} (expected exec_NNN_… or run_NNN)")
            raise typer.Exit(1)
        if not RunContext.exists(run_id):
            console.print(
                f"[red]Run not found:[/red] {run_id}\n"
                "  Create via GUI (ASSETS/ → New execution) or omit --run-id to allocate a new exec_* folder."
            )
            raise typer.Exit(1)
        ctx = RunContext(run_id, create=False)
        if not ctx.artifact_exists("run_meta.json"):
            cfg = merged_config()
            raw = Path(cfg["input_audio_path"])
            if not raw.is_absolute():
                raw = repo_root() / raw
            if raw.is_file():
                ctx.init_run_meta(str(raw.relative_to(repo_root())))
        return ctx
    cfg = merged_config()
    raw = Path(cfg["input_audio_path"])
    if not raw.is_absolute():
        raw = repo_root() / raw
    if not raw.is_file():
        console.print(f"[red]Input audio not found:[/red] {raw}")
        raise typer.Exit(1)
    wav = pipeline_wav_path(raw)
    full_hash, short_hash = source_audio_hash_pair(wav)
    new_id = RunContext.allocate_run_id(source_hash=short_hash)
    ctx = RunContext(new_id, create=True)
    ctx.init_run_meta(
        str(raw.relative_to(repo_root())),
        source_audio_hash=full_hash,
        source_audio_hash_short=short_hash,
    )
    from interview_mux.homunculus.version import stamp_run_meta
    from interview_mux.podcast_rss.settings import stamp_podcast_meta

    stamp_run_meta(ctx)
    stamp_podcast_meta(ctx)
    _emit(ctx, f"Allocated run {ctx.run_id}", level="info", stage="cli")
    return ctx


def _apply_cli_reuse_options(
    *,
    reuse_from: str | None = None,
    no_reuse_offers: bool | None = None,
) -> None:
    if no_reuse_offers is None:
        no_reuse_offers = not sys.stdin.isatty()
    configure_stage_reuse_cli(reuse_from=reuse_from, no_reuse_offers=no_reuse_offers)


def _cli_write_approval_gate(ctx: RunContext) -> None:
    pending = check_write_approval_before_execute(ctx)
    if pending:
        msg = (
            f"Write approval pending for {pending.stage_id}: "
            f"{', '.join(pending.paths)}"
        )
        _emit(ctx, msg, level="error", stage=pending.stage_id, console_markup=f"[red]{msg}[/red]")
        raise typer.Exit(1)


def run_pipeline(
    *,
    run_id: str | None = None,
    analysis_only: bool = False,
    skip_analysis: bool = False,
    from_stage: str | None = None,
    delivery_from_stage: str | None = None,
    reuse_from: str | None = None,
    no_reuse_offers: bool | None = None,
) -> RunContext:
    _apply_cli_reuse_options(reuse_from=reuse_from, no_reuse_offers=no_reuse_offers)
    ctx = _open_run(run_id)
    _emit(
        ctx,
        f"Run {ctx.run_id} → {ctx.run_dir}",
        level="info",
        stage="cli",
        console_markup=f"[bold]Run[/bold] {ctx.run_id} → {ctx.run_dir}",
    )

    with run_directory_lock(ctx.run_id):
        _cli_write_approval_gate(ctx)
        if not skip_analysis or not ctx.artifact_exists("analysis_complete.json"):
            run_analysis(ctx, from_stage=from_stage, invalidate=bool(from_stage))
            _emit(ctx, "Analysis complete.", level="success", stage="cli", console_markup="[green]Analysis complete.[/green]")
        else:
            _emit(
                ctx,
                "Skipping analysis (analysis_complete.json present).",
                level="info",
                stage="cli",
                console_markup="[dim]Skipping analysis (analysis_complete.json present).[/dim]",
            )

        missing_vo = check_g1_vo(ctx)
        if missing_vo:
            msg = (
                f"G1 gate: record VO for {missing_vo} → {ctx.path('vo_pickup')} "
                f"→ {ctx.path('understanding', 'interviewer_script.txt')}"
            )
            _emit(ctx, msg, level="warning", stage="g1_vo_pickup", console_markup=f"[yellow]G1 gate:[/yellow] record VO for {missing_vo}\n  → {ctx.path('vo_pickup')}\n  → {ctx.path('understanding', 'interviewer_script.txt')}")
            raise typer.Exit(1)

        if analysis_only:
            _emit(ctx, "--analysis-only: stopping before delivery.", level="info", stage="cli", console_markup="[dim]--analysis-only: stopping before delivery.[/dim]")
            return ctx

        run_delivery(
            ctx,
            from_stage=delivery_from_stage,
            invalidate=bool(delivery_from_stage),
        )
        _emit(
            ctx,
            f"Master: {ctx.path('master/master.wav')}",
            level="success",
            stage="delivery",
            console_markup=f"[green]Master:[/green] {ctx.path('master/master.wav')}",
        )
    return ctx


@app.command("analysis")
def analysis_cmd(
    run_id: str | None = typer.Option(None, "--run-id"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
    reuse_from: str | None = typer.Option(
        None, "--reuse-from", help="Auto-accept reuse from this exec_* when eligible"
    ),
    no_reuse_offers: bool = typer.Option(
        False,
        "--no-reuse-offers",
        help="Never pause for reuse offers (default when stdin is not a TTY)",
    ),
) -> None:
    _apply_cli_reuse_options(reuse_from=reuse_from, no_reuse_offers=no_reuse_offers or None)
    ctx = _open_run(run_id)
    _emit(
        ctx,
        f"Run {ctx.run_id} → {ctx.run_dir}",
        level="info",
        stage="cli",
        console_markup=f"[bold]Run[/bold] {ctx.run_id} → {ctx.run_dir}",
    )
    with run_directory_lock(ctx.run_id):
        _cli_write_approval_gate(ctx)
        run_analysis(ctx, from_stage=from_stage, invalidate=bool(from_stage))
    _emit(
        ctx,
        "Analysis complete. Resolve G1 if needed, then run delivery.",
        level="success",
        stage="cli",
        console_markup="[green]Analysis complete.[/green] Resolve G1 if needed, then run delivery.",
    )


@app.command("delivery")
def delivery_cmd(
    run_id: str | None = typer.Option(None, "--run-id"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
    reuse_from: str | None = typer.Option(
        None, "--reuse-from", help="Auto-accept reuse from this exec_* when eligible"
    ),
    no_reuse_offers: bool = typer.Option(
        False,
        "--no-reuse-offers",
        help="Never pause for reuse offers (default when stdin is not a TTY)",
    ),
) -> None:
    _apply_cli_reuse_options(reuse_from=reuse_from, no_reuse_offers=no_reuse_offers or None)
    ctx = _open_run(run_id)
    _emit(ctx, f"Delivery on {ctx.run_id}", level="info", stage="delivery", console_markup=f"[bold]Delivery[/bold] on {ctx.run_id}")
    with run_directory_lock(ctx.run_id):
        _cli_write_approval_gate(ctx)
        run_delivery(ctx, from_stage=from_stage, invalidate=bool(from_stage))
        _emit(
            ctx,
            f"Master: {ctx.path('master/master.wav')}",
            level="success",
            stage="delivery",
            console_markup=f"[green]Master:[/green] {ctx.path('master/master.wav')}",
        )


# Backward-compat alias
@app.command("flow", hidden=True)
def flow_cmd(
    run_id: str | None = typer.Option(None, "--run-id"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
    flow: str | None = typer.Option(None, "--flow", help="Ignored — single delivery path"),
    reuse_from: str | None = typer.Option(None, "--reuse-from"),
    no_reuse_offers: bool = typer.Option(False, "--no-reuse-offers"),
) -> None:
    delivery_cmd(
        run_id=run_id,
        from_stage=from_stage,
        reuse_from=reuse_from,
        no_reuse_offers=no_reuse_offers,
    )


@app.command("serve")
def serve_cmd(
    port: int | None = typer.Option(None, "--port", help="Web GUI port (default from config)"),
    host: str = typer.Option("127.0.0.1", "--host"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser tab"),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Open the GUI deep-linked to an existing execution (/?run=…)",
    ),
) -> None:
    """Launch the web GUI."""
    import webbrowser
    from urllib.parse import quote

    from interview_mux.config import merged_config

    from interview_mux.application_session import on_server_start

    cfg = merged_config()
    chosen_port = port or int(cfg.get("web_port", 8765))
    url = f"http://{host}:{chosen_port}"
    if run_id:
        from interview_mux.assets_ephemeral_cleanup import executions_root, is_product_execution_dir

        if not is_product_execution_dir(run_id):
            raise typer.BadParameter(f"Invalid execution id: {run_id}")
        run_dir = executions_root(cfg) / run_id
        if not run_dir.is_dir():
            raise typer.BadParameter(f"Execution not found: {run_dir}")
        url = f"{url}/?run={quote(run_id, safe='')}"
    on_server_start(port=chosen_port, host=host)

    from interview_mux.gui_job_reconcile import reconcile_stale_jobs
    from interview_mux.process_cleanup import kill_stage_workers

    orphans = kill_stage_workers()
    if orphans:
        console.print(
            f"[yellow]Stopped {orphans} orphan stage worker(s) from a prior session.[/yellow]"
        )

    reconciled = reconcile_stale_jobs()
    if reconciled:
        console.print(
            f"[yellow]Reconciled {reconciled} stale background job(s) "
            f"(server restart).[/yellow]"
        )

    try:
        from interview_mux.driver_singleton import on_serve_restart_harden

        harden = on_serve_restart_harden()
        hydrated = harden.get("hydrated_runs") or []
        cleared = harden.get("stale_claims_cleared") or []
        if hydrated or cleared:
            console.print(
                f"[yellow]Restart harden: hydrated {len(hydrated)} run(s), "
                f"cleared {len(cleared)} stale driver claim(s).[/yellow]"
            )
    except Exception as exc:
        console.print(f"[dim]Restart harden skipped: {exc}[/dim]")

    if not no_browser:
        def _open() -> None:
            import time

            time.sleep(0.8)
            webbrowser.open(url)

        import threading

        threading.Thread(target=_open, daemon=True).start()

    from interview_mux.process_logging import configure_process_logging, serve_uvicorn_options

    configure_process_logging()
    console.print(f"[bold green]Web GUI[/bold green] → {url}")
    import uvicorn

    from interview_mux.web.server import create_app

    uvicorn.run(create_app(), host=host, port=chosen_port, **serve_uvicorn_options())


@app.command("orchestrate")
def orchestrate_cmd(
    run_id: str | None = typer.Option(None, "--run-id", help="Existing run to drive"),
    mode: str = typer.Option("full-auto", "--mode", help="full-auto | partially-accelerated"),
    input_audio: str | None = typer.Option(
        None, "--input", help="Create a new run from this audio (under ASSETS/input/)"
    ),
    poll_sec: float = typer.Option(5.0, "--poll-sec", help="Gate poll interval in seconds"),
) -> None:
    """Drive a run in this process; the GUI is used only at G0 and the final sign-off.

    Replaces the job-API driver (tools/full_auto_driver.py): stages never run
    inside the web server. See interview_mux.orchestrator.
    """
    from interview_mux.full_auto_launch import normalize_run_mode
    from interview_mux.orchestrator import MODES, orchestrate

    run_mode = normalize_run_mode(mode)
    if run_mode not in MODES:
        console.print(f"[red]--mode must be one of {sorted(MODES)}[/red]")
        raise typer.Exit(2)
    if run_id and input_audio:
        console.print("[red]Pass --run-id or --input, not both[/red]")
        raise typer.Exit(2)
    if run_id:
        ctx = _open_run(run_id)
        _stamp_run_mode(ctx, run_mode)
    elif input_audio:
        ctx = _create_run_for_input(input_audio, run_mode=run_mode)
    else:
        console.print("[red]--input is required to create a run[/red]")
        raise typer.Exit(2)
    raise typer.Exit(orchestrate(ctx.run_id, mode=run_mode, poll_sec=poll_sec))


def _stamp_run_mode(ctx: RunContext, run_mode: str) -> None:
    def _mode(meta: dict) -> None:
        meta["run_mode"] = run_mode
        meta["full_auto"] = run_mode == "full-auto"
        meta["partial_auto"] = run_mode == "partially-accelerated"

    ctx.mutate_run_meta(_mode)


def _create_run_for_input(input_audio: str, *, run_mode: str) -> RunContext:
    raw = Path(input_audio)
    if not raw.is_absolute():
        raw = repo_root() / raw
    if not raw.is_file():
        console.print(f"[red]Input audio not found:[/red] {raw}")
        raise typer.Exit(1)
    wav = pipeline_wav_path(raw)
    full_hash, short_hash = source_audio_hash_pair(wav)
    new_id = RunContext.allocate_run_id(source_hash=short_hash)
    ctx = RunContext(new_id, create=True)
    ctx.init_run_meta(
        str(raw.relative_to(repo_root())),
        source_audio_hash=full_hash,
        source_audio_hash_short=short_hash,
    )
    from interview_mux.homunculus.version import stamp_run_meta
    from interview_mux.podcast_rss.settings import stamp_podcast_meta

    stamp_run_meta(ctx)
    stamp_podcast_meta(ctx)
    _stamp_run_mode(ctx, run_mode)
    try:
        from interview_mux.application_session import set_active_execution

        set_active_execution(ctx.run_id, input_audio_path=str(raw), source_locked=True)
    except Exception:
        pass
    _emit(ctx, f"Allocated run {ctx.run_id} ({run_mode})", level="info", stage="cli")
    return ctx


@app.command("run")
def run_cmd(
    run_id: str | None = typer.Option(None, "--run-id"),
    analysis_only: bool = typer.Option(False, "--analysis-only"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
    delivery_from_stage: str | None = typer.Option(None, "--delivery-from-stage"),
    flow_from_stage: str | None = typer.Option(None, "--flow-from-stage", hidden=True),
) -> None:
    """Run analysis then delivery (same as default with no subcommand)."""
    run_pipeline(
        run_id=run_id,
        analysis_only=analysis_only,
        skip_analysis=skip_analysis,
        from_stage=from_stage,
        delivery_from_stage=delivery_from_stage or flow_from_stage,
    )


def analysis_main() -> None:
    sys.argv = ["interview-mux", "analysis", *sys.argv[1:]]
    app()


def flow_main() -> None:
    sys.argv = ["interview-mux", "delivery", *sys.argv[1:]]
    app()
