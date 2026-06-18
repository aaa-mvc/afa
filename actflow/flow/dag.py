"""DAG representation for compiled flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DAGStep:
    """A single step in the compiled DAG."""

    name: str
    action_name: str  # references ActionDef.name
    depends_on: list[str] = field(default_factory=list)
    is_branch_condition: Optional[str] = None  # lambda source code if a branch node
    is_endpoint: bool = False
    action_def: Any = None  # the ActionDef instance (set by Flow.compile)


@dataclass
class DAGBranch:
    """A conditional branch in the DAG."""

    condition_source: str  # lambda source
    true_step: str
    false_step: str


@dataclass
class DAG:
    """Compiled directed acyclic graph of a Flow."""

    name: str
    version: str
    steps: list[DAGStep] = field(default_factory=list)
    branches: list[DAGBranch] = field(default_factory=list)
    entry_step: Optional[str] = None
    state_variables: list[str] = field(default_factory=list)

    def validate(self) -> "ValidationReport":
        """Run all static checks on this DAG."""
        errors: list[str] = []
        warnings: list[str] = []

        step_names = {s.name for s in self.steps}

        # orphan detection: a step is unreachable if there's no path from
        # the entry step to it (following depends_on edges forward).
        reachable: set[str] = set()
        if self.entry_step:
            queue = [self.entry_step]
            while queue:
                current = queue.pop(0)
                if current in reachable:
                    continue
                reachable.add(current)
                # steps that depend on current are reachable
                for s in self.steps:
                    if current in s.depends_on:
                        queue.append(s.name)

        orphans = step_names - reachable
        if orphans:
            warnings.append(f"Unreachable steps: {', '.join(sorted(orphans))}")

        # deadlock detection (simple cycle check)
        visited: set[str] = set()
        visiting: set[str] = set()

        def has_cycle(name: str) -> bool:
            if name in visiting:
                return True
            if name in visited:
                return False
            visiting.add(name)
            step = next((s for s in self.steps if s.name == name), None)
            if step:
                for dep in step.depends_on:
                    if dep in step_names and has_cycle(dep):
                        return True
            for b in self.branches:
                if b.condition_source and has_cycle(b.true_step):
                    return True
                if b.condition_source and has_cycle(b.false_step):
                    return True
            visiting.discard(name)
            visited.add(name)
            return False

        for name in step_names:
            if has_cycle(name):
                errors.append(f"Cycle detected involving step '{name}'")
                break

        is_valid = len(errors) == 0
        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            step_count=len(self.steps),
        )


@dataclass
class ValidationReport:
    """Result of DAG validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    step_count: int = 0

    @property
    def schema_aligned(self) -> bool:
        """Alias for is_valid (backward compat)."""
        return self.is_valid

    @property
    def orphan_steps(self) -> bool:
        """True if any warnings mention unreachable steps."""
        return any("Unreachable" in w for w in self.warnings)

    @property
    def deadlocks(self) -> bool:
        """True if any errors mention cycles."""
        return any("Cycle" in e for e in self.errors)
