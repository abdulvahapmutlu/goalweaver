from __future__ import annotations

from typing import Any

from ..agent import BaseAgent
from ..llm.local_stub import LocalStub
from ..runtime import Orchestrator
from ..tools import JSONWriteTool, ToolRegistry, WebSearchTool
from ..types import Goal, Priority, StepResult


class Researcher(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        web = next(t for t in self.tools if t.name == "web_search")
        results = await web(query=goal.title, top_k=2)
        content = "\n".join(results)
        return StepResult(
            goal_id=goal.id,
            agent=self.name,
            success=True,
            content=content,
        )

    async def propose_subgoals(self, goal: Goal, result: StepResult):
        write = Goal(
            title=f"Write: {goal.title}",
            description=result.content,
            owner_agent="writer",
            priority=Priority.HIGH,
        )
        return [write]


class Writer(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        j = next(t for t in self.tools if t.name == "json_write")
        path = await j(path="artifacts/draft.json", content=goal.description[:500])
        return StepResult(
            goal_id=goal.id,
            agent=self.name,
            success=True,
            content=f"Draft at {path}",
        )

    async def propose_subgoals(self, goal: Goal, result: StepResult):
        review = Goal(
            title=f"Review: {goal.title}",
            description=result.content,
            owner_agent="critic",
        )
        return [review]


class Critic(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        verdict = "Looks coherent; add references."
        return StepResult(goal_id=goal.id, agent=self.name, success=True, content=verdict)


async def build_demo(memory) -> tuple[Orchestrator, list[Goal]]:
    llm = LocalStub()
    tools = ToolRegistry()
    tools.register(WebSearchTool("web_search", "Lightweight demo search"))
    tools.register(JSONWriteTool("json_write", "Write JSON file"))

    agents = {
        "researcher": Researcher(
            "researcher", tools=[tools.get("web_search")], memory=memory, llm=llm
        ),
        "writer": Writer("writer", tools=[tools.get("json_write")], memory=memory, llm=llm),
        "critic": Critic("critic", tools=[], memory=memory, llm=llm),
    }

    orch = Orchestrator(memory=memory, agents=agents)

    seed = [
        Goal(
            title="Contrastive learning for multimodal retrieval",
            owner_agent="researcher",
            priority=Priority.CRITICAL,
        ),
        Goal(
            title="Survey recent RAG optimizations",
            owner_agent="researcher",
            priority=Priority.HIGH,
        ),
    ]
    return orch, seed
