import asyncio

from goalweaver.examples.coding_team import build_demo
from goalweaver.memory import SharedMemory


async def main():
    mem = SharedMemory(state_path=".test_state_code.json")
    orch, goals = await build_demo(mem)
    for g in goals:
        orch.add_goal(g)
    await orch.run(batch_size=3)


asyncio.run(main())
