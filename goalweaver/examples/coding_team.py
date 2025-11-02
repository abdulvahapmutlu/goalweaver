from __future__ import annotations

import asyncio
import os
from typing import Any, cast

from ..agent import BaseAgent, Tool
from ..llm.local_stub import LocalStub
from ..runtime import Orchestrator
from ..tools import ToolRegistry
from ..types import Goal, Priority, StepResult


# -----------------------------
# Tools (local to this demo)
# -----------------------------
class CodeWriteTool(Tool):
    """Write plain-text code to a file path (creates folders)."""

    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        path = cast(str, kwargs.get("path"))
        content = cast(str, kwargs.get("content", ""))
        if not isinstance(path, str):
            raise TypeError("CodeWriteTool requires kwarg 'path: str'")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path


class UnitTestTool(Tool):
    """Run pytest if available; otherwise return a simulated pass with a note."""

    async def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        cwd = cast(str, kwargs.get("cwd", "."))
        timeout_s = int(kwargs.get("timeout_s", 20))

        env = os.environ.copy()
        # Disable environment-wide plugin autoload (often slow/heavy).
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        try:
            proc = await asyncio.create_subprocess_exec(
                "pytest",
                "-q",
                "tests",
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except TimeoutError:
                proc.kill()
                return {"returncode": 124, "stdout": "", "stderr": "pytest timed out"}
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="ignore"),
                "stderr": stderr.decode("utf-8", errors="ignore"),
            }
        except FileNotFoundError:
            return {
                "returncode": 0,
                "stdout": "[SIMULATED] pytest not found; assuming tests pass for demo.",
                "stderr": "",
            }


class StaticCheckTool(Tool):
    """
    Very light static checks: long lines, forbidden patterns, missing docstrings.
    Intended as a placeholder for ruff/mypy integration.
    """

    async def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        root = cast(str, kwargs.get("root", "gw_code"))
        max_len = int(kwargs.get("max_len", 100))
        issues: list[str] = []
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, encoding="utf-8") as f:
                        lines = f.readlines()
                    if lines and not lines[0].lstrip().startswith('"""'):
                        issues.append(f"{p}:1 Missing top-level docstring")
                    for i, line in enumerate(lines, start=1):
                        if len(line.rstrip("\n")) > max_len:
                            issues.append(f"{p}:{i} Line exceeds {max_len} chars")
                        if "print(" in line and "__main__" not in "".join(lines[:5]):
                            issues.append(f"{p}:{i} Avoid stray print() in library code")
                except Exception as e:
                    issues.append(f"{p}:0 Read error: {e}")
        return {"issues": issues, "ok": len(issues) == 0}


# -----------------------------
# Agents
# -----------------------------
class ArchitectAgent(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        spec = (
            f"Design spec for: {goal.title}\n"
            "Requirements:\n"
            "- Clean, documented Python implementation.\n"
            "- Deterministic behavior, unit tests, and basic style checks.\n"
        )
        return StepResult(goal_id=goal.id, agent=self.name, success=True, content=spec)

    async def propose_subgoals(self, goal: Goal, result: StepResult) -> list[Goal]:
        title = goal.title
        impl = Goal(
            title=f"Implement: {title}",
            description=result.content,
            owner_agent="coder",
            priority=Priority.CRITICAL,
            dependencies=[goal.id],
        )
        tests = Goal(
            title=f"Write tests: {title}",
            description=result.content,
            owner_agent="tester",
            priority=Priority.HIGH,
            dependencies=[goal.id],
        )
        review = Goal(
            title=f"Review: {title}",
            description="Run static checks and suggest improvements",
            owner_agent="reviewer",
            priority=Priority.MEDIUM,
        )
        review.dependencies = [impl.id, tests.id]
        return [impl, tests, review]


class CoderAgent(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        write = next(t for t in self.tools if t.name == "code_write")
        files_written: list[str] = []
        nl = "\n"

        # Ensure packages exist
        await write(path="gw_code/__init__.py", content='"""generated by GoalWeaver"""')
        await write(path="tests/__init__.py", content='"""tests package marker"""')

        title_lower = goal.title.lower()
        if "slugify" in title_lower:
            path = await write(path="gw_code/utils.py", content=_slugify_impl())
            files_written.append(path)
        if "fibonacci" in title_lower:
            path = await write(path="gw_code/algos.py", content=_fibonacci_impl())
            files_written.append(path)
        if not files_written:
            path = await write(path="gw_code/module.py", content=_template_module_impl(goal.title))
            files_written.append(path)

        return StepResult(
            goal_id=goal.id,
            agent=self.name,
            success=True,
            content=nl.join(files_written),
            artifacts={"files_written": files_written},
        )


class TesterAgent(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        write = next(t for t in self.tools if t.name == "code_write")
        test_runner = next(t for t in self.tools if t.name == "unit_test")
        files_written: list[str] = []

        title_lower = goal.title.lower()
        if "slugify" in title_lower:
            p = await write(path="tests/test_utils.py", content=_tests_for_slugify())
            files_written.append(p)
        if "fibonacci" in title_lower:
            p = await write(path="tests/test_algos.py", content=_tests_for_fibonacci())
            files_written.append(p)
        if not files_written:
            p = await write(path="tests/test_module.py", content=_generic_test())
            files_written.append(p)

        result = await test_runner(cwd=".")
        ok = result.get("returncode", 1) == 0
        msg = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()

        return StepResult(
            goal_id=goal.id,
            agent=self.name,
            success=ok,
            content=msg,
            artifacts={"files_written": files_written, "test_result": result},
        )

    async def propose_subgoals(self, goal: Goal, result: StepResult) -> list[Goal]:
        if not result.success:
            fix = Goal(
                title=f"Fix failing tests for: {goal.title}",
                description=result.content,
                owner_agent="coder",
                priority=Priority.HIGH,
                dependencies=[goal.id],
            )
            return [fix]
        return []


class ReviewerAgent(BaseAgent):
    async def act(self, goal: Goal, context: dict[str, Any]) -> StepResult:
        static = next(t for t in self.tools if t.name == "static_check")
        res = await static(root="gw_code")
        ok = bool(res.get("ok", False))
        issues = res.get("issues", [])
        content = "\n".join(issues) if issues else "No issues found."
        return StepResult(
            goal_id=goal.id, agent=self.name, success=ok, content=content, artifacts=res
        )


# -----------------------------
# Demo builder
# -----------------------------
async def build_demo(memory) -> tuple[Orchestrator, list[Goal]]:
    llm = LocalStub()
    tools = ToolRegistry()
    tools.register(CodeWriteTool("code_write", "Write code files"))
    tools.register(UnitTestTool("unit_test", "Run unit tests with pytest"))
    tools.register(StaticCheckTool("static_check", "Run lightweight static checks"))

    agents = {
        "architect": ArchitectAgent("architect", tools=[], memory=memory, llm=llm),
        "coder": CoderAgent("coder", tools=[tools.get("code_write")], memory=memory, llm=llm),
        "tester": TesterAgent(
            "tester",
            tools=[tools.get("code_write"), tools.get("unit_test")],
            memory=memory,
            llm=llm,
        ),
        "reviewer": ReviewerAgent(
            "reviewer", tools=[tools.get("static_check")], memory=memory, llm=llm
        ),
    }

    orch = Orchestrator(memory=memory, agents=agents)

    seed = [
        Goal(
            title="Build utility: slugify",
            owner_agent="architect",
            priority=Priority.CRITICAL,
        ),
        Goal(
            title="Build module: fibonacci with memoization",
            owner_agent="architect",
            priority=Priority.HIGH,
        ),
    ]
    return orch, seed


# -----------------------------
# Code templates (content writers)
# -----------------------------
def _slugify_impl() -> str:
    return '''"""
Utility helpers.
"""
import unicodedata

def slugify(text: str, allow_unicode: bool = False) -> str:
    """Convert text to URL-friendly slug without regex."""
    text = str(text)
    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    out = []
    prev_dash = False
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif ch in (" ", "_", "-"):
            if out and not prev_dash:
                out.append("-")
                prev_dash = True
        else:
            # skip punctuation/symbols
            pass
    slug = "".join(out).strip("-")
    return slug

__all__ = ["slugify"]
'''


def _fibonacci_impl() -> str:
    return '''"""
Algorithms.
"""
from functools import cache

BASE_CASE_CUTOFF = 2  # avoid magic value

def fib(n: int) -> int:
    """Return the n-th Fibonacci number (0-indexed) using memoization.

    >>> fib(0)
    0
    >>> fib(1)
    1
    >>> fib(10)
    55
    """
    if n < 0:
        raise ValueError("n must be non-negative")

    @cache
    def _f(k: int) -> int:
        if k < BASE_CASE_CUTOFF:
            return k
        return _f(k - 1) + _f(k - 2)

    return _f(n)

__all__ = ["fib"]
'''


def _template_module_impl(title: str) -> str:
    return f'''"""
Module scaffold for: {title}
"""

def placeholder() -> str:
    """A placeholder function to be replaced by the coder agent."""
    return "ok"

__all__ = ["placeholder"]
'''


def _tests_for_slugify() -> str:
    return """import pytest
from gw_code.utils import slugify

def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"

@pytest.mark.parametrize("inp,exp", [
    ("Türkçe Karakter", "turkce-karakter"),
    (" multiple   spaces ", "multiple-spaces"),
    ("Café-au-lait", "cafe-au-lait"),
])
def test_slugify_variants(inp, exp):
    assert slugify(inp) == exp
"""


def _tests_for_fibonacci() -> str:
    return """import pytest
from gw_code.algos import fib

def test_fib_small():
    assert fib(0) == 0
    assert fib(1) == 1
    assert fib(10) == 55

def test_fib_raises():
    with pytest.raises(ValueError):
        fib(-1)
"""


def _generic_test() -> str:
    return """def test_placeholder():
    assert True
"""
