from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from .agent import BaseAgent
from .goal_graph import GoalGraph
from .planner import AdaptivePlanner
from .types import Event, EventType, Goal, GoalStatus, StepResult


class Orchestrator:
    """
    Coordinates agents over the goal graph. Persists a `state.json` compatible with
    the Streamlit visualizer after each phase (readiness mark, dispatch, completion).
    """

    def __init__(
        self,
        *,
        memory,
        agents: dict[str, BaseAgent],
        state_path: str = "state.json",
    ):
        self.memory = memory
        self.agents: dict[str, BaseAgent] = agents
        self.graph = GoalGraph()
        self.planner = AdaptivePlanner(self.graph)
        self.state_path = Path(state_path)
        self._events: list[Event] = []

    # ── building the graph ────────────────────────────────────────────────────────
    def add_goal(self, goal: Goal):
        self.graph.add_goal(goal)
        self._events.append(Event(type=EventType.GOAL_ADDED, payload=goal.model_dump()))

    def add_dependency(self, goal_id: str, depends_on_id: str):
        self.graph.add_dependency(goal_id, depends_on_id)

    # ── persistence helpers ───────────────────────────────────────────────────────
    async def _export_logs(self) -> list[dict[str, Any]]:
        """
        Try common memory APIs to export logs; fall back to empty list.
        """
        for attr in ("export_logs", "get_logs", "dump_logs"):
            fn = getattr(self.memory, attr, None)
            if callable(fn):
                try:
                    logs = fn()
                    return list(logs)
                except Exception:
                    pass
        return []

    async def _write_state(self) -> None:
        """
        Write a visualizer-friendly JSON snapshot: {'goals': [...], 'logs': [...]}
        """
        payload = self.graph.to_state()
        payload["logs"] = await self._export_logs()
        with suppress(Exception):
            self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ── main loop ────────────────────────────────────────────────────────────────
    async def run(self, *, batch_size: int = 3):
        idle_loops = 0
        max_idle_loops = 200  # ~10 seconds at 0.05s per loop

        while True:
            # 1) recompute READY/PENDING and persist
            self.graph.recompute_readiness()
            await self._write_state()

            # anything left to do?
            pending = [
                g
                for g in self.graph.goals()
                if g.status not in {GoalStatus.DONE, GoalStatus.FAILED}
            ]
            if not pending:
                break

            # pick batch (planner should prefer READY)
            batch = self.planner.next_batch(k=batch_size)

            if not batch:
                # Either waiting for running tasks or stuck on deps.
                idle_loops += 1
                if idle_loops >= max_idle_loops:
                    # mark all remaining as failed due to blocked deps
                    for g in pending:
                        self.graph.mark_done(g.id, success=False)
                        await self.memory.append_log(
                            {
                                "goal": g.id,
                                "agent": "orchestrator",
                                "success": False,
                                "note": "stalled/blocked",
                            }
                        )
                    await self._write_state()
                    break
                await asyncio.sleep(0.05)
                continue

            idle_loops = 0

            # 2) transition batch to IN_PROGRESS and persist
            for g in batch:
                self.graph.mark_in_progress(g.id)
            await self._write_state()

            # 3) run goals concurrently
            tasks = [self._run_goal(g) for g in batch]
            await asyncio.gather(*tasks)

        await self.memory.bump_metric("runs_completed", 1)
        await self._write_state()

    # ── per-goal execution ───────────────────────────────────────────────────────
    async def _run_goal(self, goal: Goal):
        # default owner if unspecified
        if goal.owner_agent is None:
            goal.owner_agent = next(iter(self.agents))

        agent = self.agents[goal.owner_agent]

        # ensure IN_PROGRESS before calling the agent (idempotent)
        self.graph.mark_in_progress(goal.id)
        await self._write_state()

        ctx = {"world": await self.memory.get("world", {})}
        result: StepResult = await agent.act(goal, ctx)
        await agent.reflect(goal, result)

        # Accept result, persist
        self.graph.mark_done(goal.id, result.success)
        await self.memory.append_log(
            {"goal": goal.id, "agent": agent.name, "success": result.success}
        )
        await self.memory.record_artifact(f"result:{goal.id}", result.model_dump())
        await self._write_state()

        # Handle subgoals
        subs: list[Goal] = await agent.propose_subgoals(goal, result)
        for sub in subs:
            self.add_goal(sub)
            for d in sub.dependencies or []:
                self.add_dependency(sub.id, d)

        self._events.append(Event(type=EventType.RESULT_EMITTED, payload=result.model_dump()))
