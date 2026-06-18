"""Trace and state snapshot data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepTrace:
    """Record of a single step execution."""

    step_name: str
    action_name: str
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = False
    error: str | None = None
    state_snapshot_before: dict[str, Any] = field(default_factory=dict)
    state_snapshot_after: dict[str, Any] = field(default_factory=dict)

    @property
    def step_names(self) -> list[str]:
        """Compatibility: return self as a single-element list for batch operations."""
        return [self.step_name]


@dataclass
class FlowTrace:
    """Full trace of a flow execution."""

    flow_name: str
    flow_version: str
    status: str = "pending"  # pending | running | completed | failed
    steps: list[StepTrace] = field(default_factory=list)
    branch_taken: str | None = None
    total_duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        """Overall success rate."""
        if not self.steps:
            return False
        return all(s.success for s in self.steps)

    @property
    def step_names(self) -> list[str]:
        """All step names in execution order."""
        return [s.step_name for s in self.steps]

    def to_dict(self) -> dict[str, Any]:
        """Serializable summary."""
        return {
            "flow_name": self.flow_name,
            "flow_version": self.flow_version,
            "status": self.status,
            "branch_taken": self.branch_taken,
            "total_duration_ms": self.total_duration_ms,
            "step_count": len(self.steps),
            "success_rate": sum(1 for s in self.steps if s.success) / max(len(self.steps), 1),
            "steps": [
                {
                    "step_name": s.step_name,
                    "action_name": s.action_name,
                    "duration_ms": s.duration_ms,
                    "success": s.success,
                    "error": s.error,
                }
                for s in self.steps
            ],
        }
