from goalweaver.goal_graph import GoalGraph
from goalweaver.types import Goal


def test_ready_goals_simple():
    g = GoalGraph()
    a = Goal(title="A")
    b = Goal(title="B", dependencies=[a.id])

    g.add_goal(a)
    g.add_goal(b)
    g.add_dependency(b.id, a.id)

    ready = g.ready_goals()
    assert a in ready and b not in ready

    g.mark_done(a.id, True)
    ready2 = g.ready_goals()
    assert any(x.id == b.id for x in ready2)
