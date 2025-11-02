from __future__ import annotations

import abc
from collections.abc import Iterable
from typing import Any

from .types import Goal, StepResult


class BaseAgent(abc.ABC):
    """Abstract agent with basic lifecycle hooks."""

    name: str

    def __init__(self, name: str, *, tools: Iterable[Tool] | None = None, memory=None, llm=None):
        self.name = name
        self.tools = list(tools or [])
        self.memory = memory
        self.llm = llm

    @abc.abstractmethod
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        """Perform one step toward the goal and return a StepResult."""
        raise NotImplementedError

    async def reflect(self, goal: Goal, result: StepResult) -> None:
        """Optional post-step reflection."""
        if self.memory:
            await self.memory.append_log(
                {
                    "agent": self.name,
                    "goal": goal.id,
                    "note": f"Reflection: success={result.success}",
                }
            )

    async def propose_subgoals(self, goal: Goal, result: StepResult) -> list[Goal]:
        """Optional subgoal proposal."""
        return []


class Tool(abc.ABC):
    """Callable tool interface used by agents."""

    name: str
    description: str

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abc.abstractmethod
    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Run the tool. Subclasses may use specific kwargs internally."""
        raise NotImplementedError
