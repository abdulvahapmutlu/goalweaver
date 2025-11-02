from __future__ import annotations

import abc


class LLM(abc.ABC):
    @abc.abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 512) -> str: ...

    @abc.abstractmethod
    async def embed(self, text: str) -> list[float]: ...
