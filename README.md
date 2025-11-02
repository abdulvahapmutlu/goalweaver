# GoalWeaver — Adaptive Goal Planner for Multi-Agent Systems

GoalWeaver is a compact, production-grade toolkit for **agentic AI**. It turns high-level objectives into a **DAG of goals**, schedules them adaptively, routes each goal to the right **agent**, and **persists** progress so you can **visualize** the run in real time.

[![ci](https://img.shields.io/github/actions/workflow/status/<OWNER>/<REPO>/release.yml?branch=main&label=ci)](https://github.com/<OWNER>/<REPO>/actions/workflows/release.yml)
[![release](https://img.shields.io/github/v/tag/<OWNER>/<REPO>?label=release)](https://github.com/<OWNER>/<REPO>/releases)

[![PyPI - Version](https://img.shields.io/pypi/v/goalweaver?label=pypi&cacheSeconds=300&v=1)](https://pypi.org/project/goalweaver/)
[![Python Versions](https://img.shields.io/pypi/pyversions/goalweaver)](https://pypi.org/project/goalweaver/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

- ⚙️ **Core**: DAG planner, orchestrator, memory, typed agents & tools  
- 👥 **Examples**: *research team* & *coding team* mini-workflows  
- 📊 **Visualizer**: Streamlit app for logs, dependency graph, artifacts  
- 🧪 **Quality**: ruff + black + mypy + pytest + pre-commit  
- 🚀 **Release**: Tag-driven CI/CD (PyPI/TestPyPI + GitHub Release)

> Works on **Python 3.10+** (typed for 3.11/3.12).

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [CLI](#cli)
- [Visualizer](#visualizer)
- [Concepts & Architecture](#concepts--architecture)
- [Write Your Own Agents & Tools](#write-your-own-agents--tools)
- [State & Persistence](#state--persistence)
- [Testing & Quality](#testing--quality)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Adaptive planning** over a **DAG** (NetworkX), honoring dependencies.
- **Orchestrator** with batching, **stall failsafe**, event logging, and artifact capture.
- **Shared memory** with atomic state persistence consumable by a visual dashboard.
- **Typed agents & tools** with minimal ceremony; easy to extend.
- **Streamlit visualizer** to filter, inspect, and understand execution.
- **Batteries-included dev tooling** (pre-commit, ruff, black, mypy, pytest).
- **Release workflow**: tag-driven publish to PyPI/TestPyPI + GitHub Releases.

---

## Quick Start

```
# 1) Clone & enter
git clone https://github.com/abdulvahapmutlu/goalweaver.git
cd goalweaver

# 2) (Optional) Create & activate venv
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# 3) Install package (editable mode enables CLI)
pip install -e .

# 4) (Optional) Dev tools & hooks
pip install pre-commit ruff black mypy pytest
pre-commit install
```

Run a demo and persist live state:

```
goalweaver coding-demo --state-file state.json
# or
goalweaver research-demo --state-file state.json
```

---

## CLI

The CLI uses **Typer**.

```
goalweaver --help
```

Common commands:

```
# Coding workflow (architect → coder → tester → reviewer)
goalweaver coding-demo --state-file state.json --batch-size 3

# Research workflow (researcher → writer → critic)
goalweaver research-demo --state-file state.json --batch-size 3
```

**Flags**

* `--state-file`: path to the JSON state (goals, logs, artifacts, metrics)
* `--batch-size`: scheduler concurrency per iteration (default: 3)

---

## Visualizer

Inspect runs via Streamlit:

```
# Option A: choose state file in the app
streamlit run goalweaver/visualizer/app.py

# Option B: preconfigure via env var (still editable in the app)
$env:GOALWEAVER_STATE="state.json"
streamlit run goalweaver/visualizer/app.py
```

**What you get**

* **Logs table** (agent, goal, success, notes)
* **Interactive graph** (Plotly): status filters, layout selection, seed
* **Artifacts section** (JSON-friendly; extendable viewers)
* **Debug**: peek first 30 lines of the state file

> If the graph appears empty, verify the `state.json` path and expand the status filter to include `PENDING/READY/IN_PROGRESS`.

---

## Concepts & Architecture

```
Goal (id, title, status, dependencies, owner_agent)
   └── stored in GoalGraph (networkx.DiGraph) as a DAG

AdaptivePlanner
   └── selects next READY batch (topological + heuristics)

Orchestrator
   ├── sets IN_PROGRESS, calls agent.act()
   ├── persists logs/artifacts/metrics via SharedMemory
   ├── calls agent.reflect(), handles propose_subgoals()
   └── writes state.json snapshots for the visualizer

SharedMemory
   ├── append_log() / record_artifact() / bump_metric()
   ├── export_logs() for orchestrator
   └── atomic JSON merge (preserves 'goals')
```

**Status lifecycle**: `PENDING → READY → IN_PROGRESS → DONE/FAILED`
**Edges**: point from **dependency → goal**.

The orchestrator includes:

* **Stall failsafe** (detects idle loops; marks blocked goals as failed with a log note).
* **Batch scheduling** (configurable).
* **Event emission** for the visualizer (logs & artifacts).

---

## Write Your Own Agents & Tools

### Agents

Implement `BaseAgent` (see `goalweaver/agent.py`):

```
from typing import Any
from goalweaver.agent import BaseAgent
from goalweaver.types import Goal, StepResult

class MyAgent(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        # Do work (call tools, LLMs, APIs…)
        content = f"Completed: {goal.title}"
        return StepResult(goal_id=goal.id, agent=self.name, success=True, content=content)

    async def reflect(self, goal: Goal, result: StepResult) -> None:
        if self.memory:
            await self.memory.append_log({
                "goal": goal.id, "agent": self.name, "success": result.success, "note": "reflect"
            })

    async def propose_subgoals(self, goal: Goal, result: StepResult):
        # Optionally create new goals to extend the DAG
        return []
```

### Tools

Implement `Tool` with a flexible `__call__(**kwargs)`:

```
from typing import Any
from goalweaver.agent import Tool

class WriteJSON(Tool):
    name = "json_write"
    description = "Write a JSON artifact under artifacts/"

    async def __call__(self, **kwargs: Any) -> Any:
        path = kwargs.get("path", "artifacts/out.json")
        content = kwargs.get("content", {})
        import json, os
        os.makedirs("artifacts", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
        return path
```

Register tools in your agents and pass the agents to the `Orchestrator`.

---

## State & Persistence

`goalweaver/memory.py` persists a merged, atomic snapshot to `state.json`:

```json
{
  "goals": [
    { "id": "g1", "title": "Do X", "status": "READY", "dependencies": [] }
  ],
  "logs": [
    { "goal": "g1", "agent": "coder", "success": true, "note": "test pass" }
  ],
  "artifacts": { "result:g1": { "summary": "..." } },
  "metrics": { "runs_completed": 1 }
}
```

* **Orchestrator** controls **goals** & **events**.
* **Memory** owns **logs / artifacts / metrics** and merges them into the file.
* **Visualizer** normalizes status names and is resilient to schema variants.

> Store arbitrary JSON-serializable artifacts using your own keys (e.g., `"result:<goal_id>"`).

---

## Testing & Quality

```
# Full quality gate
pre-commit run --all-files

# Unit tests
pytest -q
```

Includes:

* **ruff** (lint, import sort, pyupgrade, bugbear, etc.)
* **black** (line length 100)
* **mypy** (type safety on public APIs)
* **pytest** (unit tests in `tests/` and example sanity checks)

---

## Troubleshooting

**Visualizer shows an empty graph**

* Check the `state.json` path in the sidebar or set `GOALWEAVER_STATE`.
* Include more statuses in the filter (e.g., `PENDING/READY/IN_PROGRESS`).
* Ensure a recent demo wrote goals to the file.

**Logs not appearing**

* The default memory exports logs. If you customize it, provide one of:

  * `export_logs()` / `get_logs()` / `dump_logs()` returning `list[dict]`, or
  * an attribute `logs` / `_logs`, or
  * store `"logs"` inside the state dict.

**Run stalls**

* The stall failsafe marks blocked goals as failed after repeated idle loops.
* Check logs for `"stalled/blocked"`; ensure dependencies are satisfiable.

**Windows CRLF warnings**

* Add a `.gitattributes`:

  ```
  * text=auto eol=lf
  *.ps1 text eol=crlf
  *.bat text eol=crlf
  ```
---

## License

This project is licensed under MIT.

---

