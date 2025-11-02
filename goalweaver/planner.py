from __future__ import annotations

from .goal_graph import GoalGraph
from .types import Goal, PlanRewrite


class AdaptivePlanner:
    """Chooses next goals and rewrites plan when context changes.

    Basic heuristic: prioritize (priority, small in-degree, earlier creation).
    """

    def __init__(self, graph: GoalGraph):
        self.graph = graph

    def next_batch(self, k: int = 3) -> list[Goal]:
        ready = self.graph.ready_goals()
        ready.sort(key=lambda g: (-int(g.priority), len(g.dependencies)))
        return ready[:k]

    def rewrite(self, signal: dict) -> PlanRewrite:
        # Placeholder: in a real system, use LLM + embeddings to revise goals.
        rationale = f"Rewrite triggered by signal: {signal.get('reason', 'unknown')}"
        # Example: if many failures, downgrade batch size
        changes = {"batch_size": 2} if signal.get("failures", 0) > 0 else {}
        return PlanRewrite(rationale=rationale, changes=changes)
