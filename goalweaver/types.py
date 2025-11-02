from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Priority(int, Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class GoalStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


class EventType(str, Enum):
    GOAL_ADDED = "goal_added"
    GOAL_UPDATED = "goal_updated"
    RESULT_EMITTED = "result_emitted"
    SUBGOALS_ADDED = "subgoals_added"
    PLAN_REWRITTEN = "plan_rewritten"


class Goal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    owner_agent: str | None = None
    priority: Priority = Priority.MEDIUM
    status: GoalStatus = GoalStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StepResult(BaseModel):
    goal_id: str
    agent: str
    success: bool
    content: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)
    cost_tokens: int = 0
    latency_ms: int = 0


class Event(BaseModel):
    type: EventType
    payload: dict[str, Any]
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlanRewrite(BaseModel):
    rationale: str
    changes: dict[str, Any]
