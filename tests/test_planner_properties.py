from goalweaver.goal_graph import GoalGraph
from goalweaver.planner import AdaptivePlanner
from goalweaver.types import Goal, Priority


def test_planner_prioritizes_high_priority():
    g = GoalGraph()
    goals = []
    for i in range(5):
        pr = Priority.CRITICAL if i == 0 else Priority.LOW
        goal = Goal(title=f"G{i}", priority=pr)
        g.add_goal(goal)
        goals.append(goal)
    p = AdaptivePlanner(g)
    batch = p.next_batch(k=1)
    assert batch and batch[0].priority == Priority.CRITICAL
