from __future__ import annotations

import sys

import typer
from rich.console import Console

from interview_mux.gates import check_g1_vo, set_selected_flow
from interview_mux.pipeline import run_analysis, run_flow1, run_flow2
from interview_mux.run_context import RunContext

app = typer.Typer(help="interview_helper_mux pipeline")
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    flow: str | None = typer.Option(None, "--flow", help="flow1 or flow2 (G2)"),
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


def run_pipeline(
    *,
    flow: str | None = None,
    run_id: str | None = None,
    analysis_only: bool = False,
    skip_analysis: bool = False,
    from_stage: str | None = None,
    flow_from_stage: str | None = None,
) -> RunContext:
    ctx = RunContext(run_id)
    console.print(f"[bold]Run[/bold] {ctx.run_id} → {ctx.run_dir}")

    if not skip_analysis or not ctx.path("analysis_complete.json").is_file():
        run_analysis(ctx, from_stage=from_stage)
        console.print("[green]Analysis complete.[/green]")
    else:
        console.print("[dim]Skipping analysis (analysis_complete.json present).[/dim]")

    missing_vo = check_g1_vo(ctx)
    if missing_vo:
        console.print(
            f"[yellow]G1 gate:[/yellow] record VO for {missing_vo}\n"
            f"  → {ctx.path('vo_pickup')}\n"
            f"  → {ctx.path('understanding', 'interviewer_script.txt')}"
        )
        raise typer.Exit(1)

    if analysis_only:
        console.print("[dim]--analysis-only: stopping before flow.[/dim]")
        return ctx

    chosen = flow
    if not chosen:
        console.print("Choose output flow: [bold]flow1[/bold] (full podcast) or [bold]flow2[/bold] (highlight reel)")
        try:
            chosen = typer.prompt("flow", default="flow1").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[red]Aborted.[/red]")
            raise typer.Exit(1) from None

    if chosen not in ("flow1", "flow2"):
        console.print(f"[red]Invalid flow: {chosen}[/red] (use flow1 or flow2)")
        raise typer.Exit(1)

    set_selected_flow(ctx, chosen)
    console.print(f"[bold]Flow[/bold] {chosen}")
    if chosen == "flow1":
        run_flow1(ctx, from_stage=flow_from_stage)
        console.print(f"[green]Master:[/green] {ctx.path('flow_1_master/master.wav')}")
    else:
        run_flow2(ctx, from_stage=flow_from_stage)
        console.print(f"[green]Master:[/green] {ctx.path('flow_2_highlights/master.wav')}")
    return ctx


@app.command("analysis")
def analysis_cmd(
    run_id: str | None = typer.Option(None, "--run-id"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
) -> None:
    ctx = RunContext(run_id)
    console.print(f"[bold]Run[/bold] {ctx.run_id} → {ctx.run_dir}")
    run_analysis(ctx, from_stage=from_stage)
    console.print("[green]Analysis complete.[/green] Resolve G1 if needed, then run flow.")


@app.command("flow")
def flow_cmd(
    flow: str = typer.Option(..., "--flow", help="flow1 or flow2"),
    run_id: str | None = typer.Option(None, "--run-id"),
    from_stage: str | None = typer.Option(None, "--from-stage"),
) -> None:
    ctx = RunContext(run_id)
    set_selected_flow(ctx, flow)
    console.print(f"[bold]Flow[/bold] {flow} on {ctx.run_id}")
    if flow == "flow1":
        run_flow1(ctx, from_stage=from_stage)
        console.print(f"[green]Master:[/green] {ctx.path('flow_1_master/master.wav')}")
    elif flow == "flow2":
        run_flow2(ctx, from_stage=from_stage)
        console.print(f"[green]Master:[/green] {ctx.path('flow_2_highlights/master.wav')}")
    else:
        raise typer.BadParameter("flow must be flow1 or flow2")


@app.command("serve")
def serve_cmd(
    port: int | None = typer.Option(None, "--port", help="Web GUI port (default from config)"),
    host: str = typer.Option("127.0.0.1", "--host"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser tab"),
) -> None:
    """Launch the web GUI."""
    import threading
    import webbrowser

    from interview_mux.config import merged_config

    from interview_mux.gui_session import touch_server_session

    cfg = merged_config()
    chosen_port = port or int(cfg.get("web_port", 8765))
    url = f"http://{host}:{chosen_port}"
    touch_server_session(port=chosen_port, host=host)

    if not no_browser:
        def _open() -> None:
            import time

            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    console.print(f"[bold green]Web GUI[/bold green] → {url}")
    import uvicorn

    from interview_mux.web.server import create_app

    uvicorn.run(create_app(), host=host, port=chosen_port, log_level="info")


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
