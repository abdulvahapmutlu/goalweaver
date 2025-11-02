from __future__ import annotations

import asyncio
import hashlib

from .base import LLM


class LocalStub(LLM):
    async def generate(self, prompt: str, max_tokens: int = 512) -> str:
        await asyncio.sleep(0.05)
        return f"[STUB COMPLETION] {prompt[:80]}..."

    async def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in h[:64]]
