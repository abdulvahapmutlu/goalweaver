from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


class SharedMemory:
    """Thread/async-safe shared state with simple persistence."""

    def __init__(self, *, state_path: str = "state.json"):
        self._state_path = Path(state_path)
        self._lock = asyncio.Lock()
        # in-memory store
        self._state: dict[str, Any] = {"logs": [], "artifacts": {}, "metrics": {}}
        # try to load prior state from disk (only keys we own)
        self._load_from_disk()

    # ── public API ────────────────────────────────────────────────────────────
    async def get(self, key: str, default=None):
        async with self._lock:
            return self._state.get(key, default)

    async def set(self, key: str, value: Any):
        async with self._lock:
            self._state[key] = value
            await self._persist()

    async def append_log(self, item: dict[str, Any]):
        async with self._lock:
            self._state.setdefault("logs", []).append(item)
            await self._persist()

    async def record_artifact(self, name: str, value: Any):
        async with self._lock:
            self._state.setdefault("artifacts", {})[name] = value
            await self._persist()

    async def bump_metric(self, name: str, inc: int = 1):
        async with self._lock:
            m = self._state.setdefault("metrics", {})
            m[name] = int(m.get(name, 0)) + inc
            await self._persist()

    # These are used by the orchestrator to harvest logs into state.json
    def export_logs(self) -> list[dict]:
        return list(self._state.get("logs", []))

    # Convenience aliases (the orchestrator probes several names)
    def get_logs(self) -> list[dict]:
        return self.export_logs()

    def dump_logs(self) -> list[dict]:
        return self.export_logs()

    # Optional attribute some codebases expect
    @property
    def logs(self) -> list[dict]:
        return self._state.setdefault("logs", [])

    # ── internal helpers ──────────────────────────────────────────────────────
    def _load_from_disk(self) -> None:
        """Load existing logs/artifacts/metrics from disk if present."""
        try:
            if not self._state_path.exists():
                return
            with self._state_path.open("r", encoding="utf-8") as f:
                on_disk = json.load(f)
            # Only merge the namespaces we own; never touch 'goals'
            if isinstance(on_disk, dict):
                if isinstance(on_disk.get("logs"), list):
                    self._state["logs"] = on_disk["logs"]
                if isinstance(on_disk.get("artifacts"), dict):
                    self._state["artifacts"] = on_disk["artifacts"]
                if isinstance(on_disk.get("metrics"), dict):
                    self._state["metrics"] = on_disk["metrics"]
        except Exception:
            # best-effort load; keep in-memory defaults on failure
            pass

    async def _persist(self) -> None:
        """
        Persist a merged view for the Streamlit dashboard.

        We read current file (if any), preserve keys we don't own (e.g., 'goals' written
        by the orchestrator), and update/overwrite only our own namespaces:
          - 'logs', 'artifacts', 'metrics'
        """
        # read existing content (best-effort)
        merged: dict[str, Any] = {}
        try:
            if self._state_path.exists():
                with self._state_path.open("r", encoding="utf-8") as f:
                    current = json.load(f)
                if isinstance(current, dict):
                    merged.update(current)
        except Exception:
            # if it's unreadable, we'll just write our own state below
            pass

        # update only our namespaces
        merged["logs"] = list(self._state.get("logs", []))
        merged["artifacts"] = dict(self._state.get("artifacts", {}))
        merged["metrics"] = dict(self._state.get("metrics", {}))

        # atomic write: tmp + replace
        tmp_path = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._state_path)
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)  # py3.11+
            except Exception:
                pass
