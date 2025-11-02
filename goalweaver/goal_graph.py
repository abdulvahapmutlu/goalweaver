from __future__ import annotations

import networkx as nx  # type: ignore[import-untyped]

from .types import Goal, GoalStatus


class GoalGraph:
    """
    DAG of Goals stored in a DiGraph. Each node keeps the Goal object in node['goal'].
    Edges are oriented as: dependency  ->  goal
    """

    def __init__(self) -> None:
        self.g = nx.DiGraph()

    # ── mutation ──────────────────────────────────────────────────────────────────
    def add_goal(self, goal: Goal) -> None:
        self.g.add_node(goal.id, goal=goal)

    def add_dependency(self, goal_id: str, depends_on_id: str) -> None:
        # depends_on -> goal
        self.g.add_edge(depends_on_id, goal_id)
        assert nx.is_directed_acyclic_graph(self.g), "Dependencies must form a DAG"

    def set_status(self, goal_id: str, status: GoalStatus) -> None:
        node = self.g.nodes[goal_id]
        goal: Goal = node["goal"]
        goal.status = status
        node["goal"] = goal

    def mark_in_progress(self, goal_id: str) -> None:
        g = self.get(goal_id)
        if g.status not in {GoalStatus.DONE, GoalStatus.FAILED}:
            self.set_status(goal_id, GoalStatus.IN_PROGRESS)

    def mark_done(self, goal_id: str, success: bool) -> None:
        self.set_status(goal_id, GoalStatus.DONE if success else GoalStatus.FAILED)

    # ── queries ───────────────────────────────────────────────────────────────────
    def goals(self) -> list[Goal]:
        return [data["goal"] for _, data in self.g.nodes(data=True)]

    def get(self, goal_id: str) -> Goal:
        return self.g.nodes[goal_id]["goal"]

    def predecessors(self, goal_id: str) -> list[str]:
        return list(self.g.predecessors(goal_id))

    # ── readiness propagation ─────────────────────────────────────────────────────
    def ready_goals(self) -> list[Goal]:
        """
        Legacy helper: sets READY for nodes whose predecessors are DONE and returns them.
        (Leaves IN_PROGRESS/DONE/FAILED untouched.)
        """
        ready: list[Goal] = []
        for n in nx.topological_sort(self.g):
            goal: Goal = self.g.nodes[n]["goal"]
            if goal.status in {
                GoalStatus.DONE,
                GoalStatus.FAILED,
                GoalStatus.IN_PROGRESS,
            }:
                continue
            preds = list(self.g.predecessors(n))
            if all(self.g.nodes[p]["goal"].status == GoalStatus.DONE for p in preds):
                goal.status = GoalStatus.READY
                ready.append(goal)
            else:
                goal.status = GoalStatus.PENDING
        return ready

    def recompute_readiness(self) -> None:
        """
        Idempotent pass: PENDING/READY nodes are recomputed based on dependency states.
        - If all predecessors DONE -> READY
        - Else -> PENDING
        - Nodes IN_PROGRESS/DONE/FAILED unchanged
        """
        for n in nx.topological_sort(self.g):
            goal: Goal = self.g.nodes[n]["goal"]
            if goal.status in {
                GoalStatus.IN_PROGRESS,
                GoalStatus.DONE,
                GoalStatus.FAILED,
            }:
                continue
            preds = list(self.g.predecessors(n))
            if all(self.g.nodes[p]["goal"].status == GoalStatus.DONE for p in preds):
                goal.status = GoalStatus.READY
            else:
                goal.status = GoalStatus.PENDING

    # ── export for visualizer ─────────────────────────────────────────────────────
    def to_state(self) -> dict[str, list[dict[str, object]]]:
        """
        Minimal serializable snapshot for the Streamlit visualizer.
        """
        goals_state: list[dict[str, object]] = []
        for n in nx.topological_sort(self.g):
            goal: Goal = self.g.nodes[n]["goal"]
            deps = list(self.g.predecessors(n))
            goals_state.append(
                {
                    "id": goal.id,
                    "title": goal.title,
                    "status": goal.status.value,
                    "dependencies": deps,
                }
            )
        return {"goals": goals_state}
