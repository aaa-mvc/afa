"""ActionFlow CLI — lightweight command-line interface.

Usage:
    actflow test flow.py          # Validate a flow definition
    actflow run flow.py           # Execute a flow (dry-run by default)
    actflow visualize flow.py     # Print Mermaid diagram
    actflow --version             # Show version
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from actflow import __version__

app = typer.Typer(
    name="actflow",
    help="ActionFlow — Stateful Agent Action Runtime",
    no_args_is_help=True,
    invoke_without_command=True,
)
console = Console()


def _load_flow_from_file(filepath: str) -> Any:
    """Dynamic import: load a Flow object from a Python file.

    Expects the file to define a module-level variable named 'flow'.
    """
    path = Path(filepath).resolve()
    if not path.exists():
        console.print(f"[red]Error:[/] file not found: {path}")
        raise typer.Exit(code=1)

    spec = importlib.util.spec_from_file_location("_user_flow", path)
    if spec is None or spec.loader is None:
        console.print(f"[red]Error:[/] cannot import {path}")
        raise typer.Exit(code=1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["_user_flow"] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "flow"):
        console.print(
            f"[red]Error:[/] {path} must define a top-level 'flow' variable"
        )
        raise typer.Exit(code=1)

    return module.flow


# ── commands ──


@app.command()
def test(
    filepath: str = typer.Argument(..., help="Path to a Python file that defines 'flow'"),
):
    """Validate a flow definition. Checks schema alignment, orphans, and deadlocks."""
    from actflow.flow.flow import Flow

    console.print(f"[bold]ActionFlow Test[/] — {filepath}")

    try:
        flow: Flow = _load_flow_from_file(filepath)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]FAIL[/] cannot load flow: {exc}")
        raise typer.Exit(code=1)

    console.print(f"  Flow: [cyan]{flow.name}[/] (v{flow.version})")
    console.print(f"  Actions: {', '.join(flow.action_names)}")

    try:
        dag = flow.compile(strict=True)
        report = dag.validate()
    except ValueError as exc:
        console.print(f"[red]FAIL[/] compilation error: {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]FAIL[/] unexpected error: {exc}")
        raise typer.Exit(code=1)

    # ── results table ──
    table = Table(title="Validation Results")
    table.add_column("Check", style="bold")
    table.add_column("Result")

    table.add_row(
        "Schema Aligned",
        "[green]PASS[/]" if report.schema_aligned else "[red]FAIL[/]",
    )
    table.add_row(
        "Orphan Steps",
        "[green]PASS[/]" if not report.orphan_steps else f"[yellow]WARN: {report.warnings}[/]",
    )
    table.add_row(
        "Deadlocks",
        "[green]PASS[/]" if not report.deadlocks else "[red]FAIL[/]",
    )
    table.add_row("Step Count", str(report.step_count))

    console.print(table)

    if report.warnings:
        console.print("\n[yellow]Warnings:[/]")
        for w in report.warnings:
            console.print(f"  • {w}")

    if report.is_valid:
        console.print("\n[green]All checks passed. Flow is valid.[/]")
    else:
        console.print("\n[red]Validation failed.[/]")
        raise typer.Exit(code=1)


@app.command()
def run(
    filepath: str = typer.Argument(..., help="Path to a Python file that defines 'flow'"),
    dry_run: bool = typer.Option(True, "--live/--dry-run", help="Run in live or dry-run mode"),
    state: str = typer.Option("{}", "--state", help="Initial state as JSON, e.g. '{\"query\": \"test\"}'"),
):
    """Execute a flow and print the trace + value report."""
    import json

    from actflow.runtime.runtime import Runtime, RuntimeMode

    console.print(f"[bold]ActionFlow Run[/] — {filepath}")

    try:
        flow = _load_flow_from_file(filepath)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]FAIL[/] cannot load flow: {exc}")
        raise typer.Exit(code=1)

    try:
        initial_state = json.loads(state)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid --state JSON: {exc}[/]")
        raise typer.Exit(code=1)

    dag = flow.compile()

    mode = RuntimeMode.DRY_RUN if dry_run else RuntimeMode.LIVE
    runtime = Runtime(dag, mode=mode)

    # auto-bind if the module has matching functions
    module = sys.modules.get("_user_flow")
    if module:
        for name in flow.action_names:
            if hasattr(module, name):
                func = getattr(module, name)
                runtime.bind(name, func)
                console.print(f"  [dim]auto-bind: {name}[/]")

    result = runtime.run(initial_state)

    console.print(f"\nStatus: [green]{result.status}[/]" if result.success else f"\nStatus: [red]{result.status}[/]")
    if result.trace:
        console.print(f"Steps: {len(result.trace.steps)}")
        console.print(f"Duration: {result.trace.total_duration_ms:.0f} ms")
        for s in result.trace.steps:
            icon = "✅" if s.success else "❌"
            console.print(f"  {icon} {s.step_name} ({s.duration_ms:.0f} ms)")
            if s.error:
                console.print(f"     [red]Error: {s.error}[/]")

    # value report
    try:
        from actflow.value.mapper import ValueMapper
        mapper = ValueMapper(flow)
        mapper.map(
            metric="success",
            source="trace.success",
        )
        if result.trace:
            report = mapper.calculate(result.trace)
            console.print(f"\n[bold]Value:[/] {report.total_value:.2f}")
    except Exception:
        pass


@app.command()
def visualize(
    filepath: str = typer.Argument(..., help="Path to a Python file that defines 'flow'"),
):
    """Print a Mermaid flowchart for the flow."""
    try:
        flow = _load_flow_from_file(filepath)
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error loading flow: {exc}[/]")
        raise typer.Exit(code=1)

    console.print(flow.visualize())


@app.callback(invoke_without_command=True)
def callback(
    version: bool = typer.Option(False, "--version", help="Show version"),
):
    if version:
        console.print(f"actflow v{__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
