"""Flow — orchestrate actions into a compilable, executable pipeline."""

from __future__ import annotations

from typing import Any, Callable, Optional

from actflow.schema.action_def import ActionDef
from actflow.flow.dag import DAG, DAGBranch, DAGStep


class Flow:
    """Declarative action pipeline.

    Example::

        flow = (
            Flow("customer_inquiry")
            .step(search)
            .step(compose, depends_on=["search"])
            .branch(when=lambda s: s["compose.confidence"] >= 0.8, then=send, else_=human)
            .compile()
        )
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._steps: list[dict[str, Any]] = []
        self._branches: list[dict[str, Any]] = []
        self._entry: Optional[str] = None

    # ── builder API ──

    def step(
        self,
        action: ActionDef,
        *,
        depends_on: Optional[list[str]] = None,
    ) -> "Flow":
        """Append an action step."""
        entry = {
            "action": action,
            "name": action.name,
            "depends_on": depends_on or [],
        }
        if self._entry is None:
            self._entry = action.name
        self._steps.append(entry)
        return self

    def branch(
        self,
        *,
        when: Callable[[dict[str, Any]], bool],
        then: ActionDef | str,
        else_: ActionDef | str,
    ) -> "Flow":
        """Add a conditional branch.

        Args:
            when: A callable that receives the current runtime state and returns bool.
            then: Action or step name to execute when condition is True.
            else_: Action or step name to execute when condition is False.
        """
        import inspect

        try:
            condition_source = inspect.getsource(when).strip()
        except (TypeError, OSError):
            condition_source = repr(when)

        self._branches.append(
            {
                "condition": when,
                "condition_source": condition_source,
                "then": then.name if isinstance(then, ActionDef) else then,
                "else": else_.name if isinstance(else_, ActionDef) else else_,
            }
        )
        return self

    # ── compilation ──

    def compile(self, *, strict: bool = True) -> DAG:
        """Compile the flow into a validated DAG.

        The compiler:
        1. Builds step nodes with dependency edges.
        2. Cross-checks that every branch target exists.
        3. Derives state variables from action I/O schemas.
        4. Runs cycle / orphan detection.

        Args:
            strict: If True, raises on validation errors.

        Returns:
            A validated DAG ready for Runtime execution.

        Raises:
            ValueError: If strict=True and the DAG has validation errors.
        """
        dag = DAG(name=self.name, version=self.version)

        # ── build steps ──
        for s in self._steps:
            dag.steps.append(
                DAGStep(
                    name=s["name"],
                    action_name=s["action"].name,
                    depends_on=s["depends_on"],
                    action_def=s["action"],
                )
            )

        # ── build branches ──
        for b in self._branches:
            dag.branches.append(
                DAGBranch(
                    condition_source=b["condition_source"],
                    true_step=b["then"],
                    false_step=b["else"],
                )
            )

        # ── derive state variables ──
        state_vars: list[str] = []
        for s in self._steps:
            action: ActionDef = s["action"]
            for key in action.input_schema:
                state_vars.append(f"{action.name}.input.{key}")
            for key in action.output_schema:
                state_vars.append(f"{action.name}.output.{key}")
        dag.state_variables = sorted(set(state_vars))

        dag.entry_step = self._entry

        # ── validate ──
        report = dag.validate()
        if strict and not report.is_valid:
            raise ValueError(
                f"Flow '{self.name}' compilation failed:\n"
                + "\n".join(f"  ERROR: {e}" for e in report.errors)
            )

        return dag

    # ── introspection ──

    @property
    def action_names(self) -> list[str]:
        """All action names in this flow (in order)."""
        return [s["action"].name for s in self._steps]

    def visualize(self) -> str:
        """Return a Mermaid flowchart string."""
        lines = ["```mermaid", "flowchart TD"]
        for s in self._steps:
            safe_name = s["name"].replace(" ", "_")
            lines.append(f"    {safe_name}[{s['name']}]")
            for dep in s.get("depends_on", []):
                safe_dep = dep.replace(" ", "_")
                lines.append(f"    {safe_dep} --> {safe_name}")
        for b in self._branches:
            lines.append(f"    %% branch: {b['condition_source']}")
        lines.append("```")
        return "\n".join(lines)
