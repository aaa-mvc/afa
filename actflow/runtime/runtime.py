"""Runtime — the execution engine for compiled Flows."""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from actflow.flow.dag import DAG
from actflow.schema.action_def import ActionDef, SideEffectLevel
from actflow.runtime.trace import FlowTrace, StepTrace


class RuntimeMode(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"


class Runtime:
    """Execute a compiled DAG, tracking state and producing traces.

    Example::

        runtime = Runtime(dag)
        runtime.bind("search_kb", my_search_fn)
        runtime.bind("compose_reply", my_compose_fn)
        result = runtime.run({"query": "退货政策"})
        print(result.trace.to_dict())
    """

    def __init__(
        self,
        dag: DAG,
        mode: RuntimeMode = RuntimeMode.LIVE,
    ):
        self.dag = dag
        self.mode = mode
        self._bindings: dict[str, Callable[..., dict[str, Any]]] = {}
        self._action_registry: dict[str, ActionDef] = {}
        self._state: dict[str, Any] = {}

    # ── binding ──

    def bind(
        self,
        action: ActionDef | str,
        func: Callable[..., dict[str, Any]],
    ) -> "Runtime":
        """Bind an ActionDef to its implementation.

        Args:
            action: An ActionDef instance or action name string.
            func: The function that executes this action.
        """
        name = action if isinstance(action, str) else action.name
        if isinstance(action, ActionDef):
            self._action_registry[name] = action
        self._bindings[name] = func
        return self

    def bind_all(self, **kwargs: ActionDef | Callable[..., dict[str, Any]]) -> "Runtime":
        """Bind multiple actions at once.

        Example::

            runtime.bind_all(
                search_kb=my_search,
                compose_reply=my_compose,
            )
        """
        for name, action_or_func in kwargs.items():
            if isinstance(action_or_func, ActionDef):
                self._action_registry[name] = action_or_func
            elif callable(action_or_func):
                self.bind(name, action_or_func)
        return self

    # ── execution ──

    def run(
        self,
        initial_state: dict[str, Any] | None = None,
        *,
        trace: bool = True,
    ) -> "RunResult":
        """Execute the flow sequentially.

        Args:
            initial_state: Seed state for the first step.
            trace: If True, record full per-step traces.

        Returns:
            RunResult with final state and execution trace.
        """
        self._state = dict(initial_state or {})
        flow_trace = FlowTrace(
            flow_name=self.dag.name,
            flow_version=self.dag.version,
            status="running",
        )

        t_start = time.perf_counter()

        try:
            for step in self.dag.steps:
                step_trace = self._execute_step(step, trace=trace)
                flow_trace.steps.append(step_trace)

                if not step_trace.success:
                    flow_trace.status = "failed"
                    break

                # propagate output into state
                prefix = f"{step.action_name}.output"
                for k, v in step_trace.output.items():
                    self._state[f"{prefix}.{k}"] = v

            else:
                flow_trace.status = "completed"

        except Exception as exc:
            flow_trace.status = "failed"
            flow_trace.steps.append(
                StepTrace(
                    step_name="<exception>",
                    action_name="<exception>",
                    success=False,
                    error=str(exc),
                )
            )

        flow_trace.total_duration_ms = (time.perf_counter() - t_start) * 1000
        return RunResult(
            state=dict(self._state),
            trace=flow_trace if trace else None,
            status=flow_trace.status,
        )

    def _execute_step(
        self,
        step,
        *,
        trace: bool = True,
    ) -> StepTrace:
        """Execute a single DAG step, with schema validation and side-effect gating."""
        action_def = self._action_registry.get(step.action_name) or step.action_def
        func = self._bindings.get(step.action_name)

        snapshot_before = dict(self._state) if trace else {}

        if func is None:
            return StepTrace(
                step_name=step.name,
                action_name=step.action_name,
                success=False,
                error=f"No binding for action '{step.action_name}'",
                state_snapshot_before=snapshot_before,
            )

        # dry-run gate
        if self.mode == RuntimeMode.DRY_RUN and action_def is not None:
            if action_def.side_effect_level not in (
                SideEffectLevel.READ_ONLY,
                SideEffectLevel.INTERNAL,
            ):
                return StepTrace(
                    step_name=step.name,
                    action_name=step.action_name,
                    success=True,
                    output={
                        k: f"<dry_run: would have produced {v.__name__}>"
                        for k, v in (action_def.output_schema or {}).items()
                    },
                    state_snapshot_before=snapshot_before,
                    state_snapshot_after=dict(self._state),
                )

        # build input from state
        step_input: dict[str, Any] = {}
        if action_def is not None:
            for key in action_def.input_schema:
                # 1. qualified: this_action.input.key
                qualified = f"{step.action_name}.input.{key}"
                if qualified in self._state:
                    step_input[key] = self._state[qualified]
                    continue
                # 2. predecessor output: if this step depends on X,
                #    check X.output.key
                for dep in step.depends_on:
                    dep_key = f"{dep}.output.{key}"
                    if dep_key in self._state:
                        step_input[key] = self._state[dep_key]
                        break
                else:
                    # 3. plain key in state (e.g. from initial state)
                    if key in self._state:
                        step_input[key] = self._state[key]

        t0 = time.perf_counter()
        try:
            # schema validation (input)
            if action_def is not None:
                action_def.validate_input(step_input)

            # execute
            output = func(**step_input)

            # schema validation (output)
            if action_def is not None:
                action_def.validate_output(output)

            duration_ms = (time.perf_counter() - t0) * 1000
            return StepTrace(
                step_name=step.name,
                action_name=step.action_name,
                input=step_input,
                output=output,
                duration_ms=duration_ms,
                success=True,
                state_snapshot_before=snapshot_before,
                state_snapshot_after=dict(self._state),
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            return StepTrace(
                step_name=step.name,
                action_name=step.action_name,
                input=step_input,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
                state_snapshot_before=snapshot_before,
            )

    # ── properties ──

    @property
    def state(self) -> dict[str, Any]:
        """Current runtime state (read-only view)."""
        return dict(self._state)


class RunResult:
    """Result of a flow execution."""

    def __init__(
        self,
        state: dict[str, Any],
        trace: FlowTrace | None,
        status: str,
    ):
        self.state = state
        self.trace = trace
        self.status = status

    @property
    def success(self) -> bool:
        return self.status == "completed"

    def __repr__(self) -> str:
        step_count = len(self.trace.steps) if self.trace else 0
        return f"RunResult(status={self.status}, steps={step_count})"
