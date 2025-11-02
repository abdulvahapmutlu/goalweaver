from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from .examples.coding_team import build_demo as build_coding_demo
from .examples.research_team import build_demo as build_research_demo
from .memory import SharedMemory

app = typer.Typer(no_args_is_help=True, add_completion=False)


async def _run(build_fn, state_file: Path, batch_size: int) -> None:
    mem = SharedMemory(state_path=str(state_file))
    orch, goals = await build_fn(mem)  # type: ignore[call-arg]
    for g in goals:
        orch.add_goal(g)
    await orch.run(batch_size=batch_size)


@app.command("demo")
def cmd_demo(
    state_file: Path = typer.Option("state.json", "-s", "--state-file", help="State file path."),
    batch_size: int = typer.Option(3, "-b", "--batch-size", min=1, help="Concurrency batch size."),
) -> None:
    """
    Run the default demo (research team).
    """
    asyncio.run(_run(build_research_demo, state_file, batch_size))


@app.command("research-demo")
def cmd_research(
    state_file: Path = typer.Option("state.json", "-s", "--state-file", help="State file path."),
    batch_size: int = typer.Option(3, "-b", "--batch-size", min=1, help="Concurrency batch size."),
) -> None:
    """Run the research team demo."""
    asyncio.run(_run(build_research_demo, state_file, batch_size))


@app.command("coding-demo")
def cmd_coding(
    state_file: Path = typer.Option("state.json", "-s", "--state-file", help="State file path."),
    batch_size: int = typer.Option(3, "-b", "--batch-size", min=1, help="Concurrency batch size."),
) -> None:
    """Run the coding team demo."""
    asyncio.run(_run(build_coding_demo, state_file, batch_size))
