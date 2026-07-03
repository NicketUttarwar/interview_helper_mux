from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from interview_mux.gates import check_g1_vo, set_selected_flow
from interview_mux.pipeline import run_analysis, run_flow1, run_flow2, run_flow3
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
    flow: str | None = typer.Option(None, "--flow", help="flow1, flow2, or flow3 (G2)"),
    run_id: str | None = typer.Option(None, "--run-id"),
    analysis_only: bool = typer.Option(False, "--analysis-only", help="Stop after analysis"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="Skip if analysis_complete.json exists"),
    from_stage: str | None = typer.Option(None, "--from-stage", help="Analysis stage to restart from"),
) -> None:
    """Default: run analysis, then flow (unless --analysis-only)."""
    if ctx.invoked_subcommand is not None:
        return
    run_pipeline(
        flow=flow,
        run_id=run_id,
        analysis_only=analysis_only,
        skip_analysis=skip_analysis,
        from_stage=from_stage,
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
    flow: str | None = None,
    run_id: str | None = None,
    analysis_only: bool = False,
    skip_analysis: bool = False,
    from_stage: str | None = None,
    flow_from_stage: str | None = None,
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
            run_analysis(ctx, from_stage=from_stage)
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
            _emit(ctx, "--analysis-only: stopping before flow.", level="info", stage="cli", console_markup="[dim]--analysis-only: stopping before flow.[/dim]")
            return ctx

        chosen = flow
        if not chosen:
            console.print(
                "Choose output flow: [bold]flow1[/bold] (full podcast), "
                "[bold]flow2[/bold] (highlight reel), or [bold]flow3[/bold] (show description)"
            )
            try:
                chosen = typer.prompt("flow", default="flow1").strip().lower()
            except (EOFError, KeyboardInterrupt):
                _emit(ctx, "Aborted.", level="warning", stage="cli", console_markup="\n[red]Aborted.[/red]")
                raise typer.Exit(1) from None

        if chosen not in ("flow1", "flow2", "flow3"):
            msg = f"Invalid flow: {chosen} (use flow1, flow2, or flow3)"
            _emit(ctx, msg, level="error", stage="g2_flow_select", console_markup=f"[red]{msg}[/red]")
            raise typer.Exit(1)

        set_selected_flow(ctx, chosen)
        _emit(ctx, f"Flow {chosen}", level="info", stage="g2_flow_select", console_markup=f"[bold]Flow[/bold] {chosen}")
        if chosen == "flow1":
            run_flow1(ctx, from_stage=flow_from_stage)
            _emit(ctx, f"Master: {ctx.path('flow_1_master/master.wav')}", level="success", stage="flow1", console_markup=f"[green]Master:[/green] {ctx.path('flow_1_master/master.wav')}")
        elif chosen == "flow2":
            run_flow2(ctx, from_stage=flow_from_stage)
            _emit(ctx, f"Master: {ctx.path('flow_2_highlights/master.wav')}", level="success", stage="flow2", console_markup=f"[green]Master:[/green] {ctx.path('flow_2_highlights/master.wav')}")
        else:
            run_flow3(ctx, from_stage=flow_from_stage)
            desc = str(ctx.path("flow_3_description/show_description.md"))
            _emit(ctx, f"Show description: {desc}", level="success", stage="flow3", console_markup=f"[green]Show description:[/green] {desc}")
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
        run_analysis(ctx, from_stage=from_stage)
    _emit(ctx, "Analysis complete. Resolve G1 if needed, then run flow.", level="success", stage="cli", console_markup="[green]Analysis complete.[/green] Resolve G1 if needed, then run flow.")


@app.command("flow")
def flow_cmd(
    flow: str = typer.Option(..., "--flow", help="flow1, flow2, or flow3"),
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
    set_selected_flow(ctx, flow)
    _emit(ctx, f"Flow {flow} on {ctx.run_id}", level="info", stage="g2_flow_select", console_markup=f"[bold]Flow[/bold] {flow} on {ctx.run_id}")
    with run_directory_lock(ctx.run_id):
        _cli_write_approval_gate(ctx)
        if flow == "flow1":
            run_flow1(ctx, from_stage=from_stage)
            _emit(ctx, f"Master: {ctx.path('flow_1_master/master.wav')}", level="success", stage="flow1", console_markup=f"[green]Master:[/green] {ctx.path('flow_1_master/master.wav')}")
        elif flow == "flow2":
            run_flow2(ctx, from_stage=from_stage)
            _emit(ctx, f"Master: {ctx.path('flow_2_highlights/master.wav')}", level="success", stage="flow2", console_markup=f"[green]Master:[/green] {ctx.path('flow_2_highlights/master.wav')}")
        elif flow == "flow3":
            run_flow3(ctx, from_stage=from_stage)
            desc = str(ctx.path("flow_3_description/show_description.md"))
            _emit(ctx, f"Show description: {desc}", level="success", stage="flow3", console_markup=f"[green]Show description:[/green] {desc}")
        else:
            raise typer.BadParameter("flow must be flow1, flow2, or flow3")


@app.command("serve")
def serve_cmd(
    port: int | None = typer.Option(None, "--port", help="Web GUI port (default from config)"),
    host: str = typer.Option("127.0.0.1", "--host"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser tab"),
) -> None:
    """Launch the web GUI."""
    import webbrowser

    from interview_mux.config import merged_config

    from interview_mux.application_session import on_server_start

    cfg = merged_config()
    chosen_port = port or int(cfg.get("web_port", 8765))
    url = f"http://{host}:{chosen_port}"
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


@app.command("run")
def run_cmd(
    flow: str | None = typer.Option(None, "--flow"),
    run_id: str | None = typer.Option(None, "--run-id"),
    analysis_only: bool = typer.Option(False, "--analysis-only"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
    flow_from_stage: str | None = typer.Option(None, "--flow-from-stage"),
) -> None:
    """Run analysis then flow (same as default with no subcommand)."""
    run_pipeline(
        flow=flow,
        run_id=run_id,
        analysis_only=analysis_only,
        skip_analysis=skip_analysis,
        from_stage=from_stage,
        flow_from_stage=flow_from_stage,
    )


def analysis_main() -> None:
    sys.argv = ["interview-mux", "analysis", *sys.argv[1:]]
    app()


def flow_main() -> None:
    sys.argv = ["interview-mux", "flow", *sys.argv[1:]]
    app()
