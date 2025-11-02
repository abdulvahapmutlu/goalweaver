from __future__ import annotations

import asyncio
from typing import Any, cast

from .agent import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        key = tool.name.lower()
        if key in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[key] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name.lower()]

    def list(self) -> list[str]:
        return sorted(self._tools.keys())


class WebSearchTool(Tool):
    async def __call__(self, *args: Any, **kwargs: Any) -> list[str]:
        # Stub for demo; integrate real search in production
        query = cast(str, kwargs.get("query"))
        if not isinstance(query, str):
            raise TypeError("WebSearchTool requires kwarg 'query: str'")
        top_k = int(kwargs.get("top_k", 3))
        await asyncio.sleep(0.05)
        return [f"Result {i} for '{query}'" for i in range(1, top_k + 1)]


class JSONWriteTool(Tool):
    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        import json
        import os

        path = cast(str, kwargs.get("path"))
        content = cast(str, kwargs.get("content", ""))
        if not isinstance(path, str):
            raise TypeError("JSONWriteTool requires kwarg 'path: str'")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"content": content}, f, ensure_ascii=False, indent=2)
        return path
