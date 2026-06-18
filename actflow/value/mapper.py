"""ValueMapper — translate flow execution traces into business value metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from actflow.flow.flow import Flow
from actflow.runtime.trace import FlowTrace, StepTrace
from actflow.value.curves import ExponentialDecay, Linear, ValueCurve


@dataclass
class MetricDef:
    """Definition of a single value metric."""

    name: str
    source: str  # dotted path into StepTrace or FlowTrace, e.g. "trace.duration_ms"
    curve: ValueCurve = field(default_factory=lambda: Linear(min_threshold=0.0, max_perfect=1.0))
    agg: str = "mean"  # mean | sum | max | min | p50 | p95 | rate
    weight: float = 1.0  # relative weight in combined score
    description: str = ""


@dataclass
class CalcStep:
    """A single step in the value calculation chain (for auditability)."""

    source: str
    samples: int
    filter: str
    agg: str
    raw_value: float
    transform: str
    transformed_value: float


@dataclass
class ValueReport:
    """The final output of ValueMapper."""

    total_value: float = 0.0
    confidence: float = 0.0
    chain: list[CalcStep] = field(default_factory=list)
    breakdown: dict[str, float] = field(default_factory=dict)
    sensitivity: dict[str, dict[str, str]] = field(default_factory=dict)
    assumptions: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"ValueReport(\n"
            f"  total_value={self.total_value:.2f},\n"
            f"  confidence={self.confidence:.2f},\n"
            f"  breakdown={self.breakdown},\n"
            f")"
        )


class ValueMapper:
    """Map flow execution traces to business value.

    Example::

        mapper = ValueMapper(flow)
        mapper.map(
            metric="response_time",
            source="trace.total_duration_ms",
            curve=ExponentialDecay(perfect=60000, half_life=300000),
        )
        report = mapper.calculate(trace)
    """

    def __init__(self, flow: Flow):
        self.flow = flow
        self._metrics: list[MetricDef] = []
        self._assumptions: dict[str, Any] = {}

    def map(
        self,
        *,
        metric: str,
        source: str,
        curve: ValueCurve | None = None,
        agg: str = "mean",
        weight: float = 1.0,
        description: str = "",
    ) -> "ValueMapper":
        """Register a metric mapping.

        Args:
            metric: Human-readable metric name.
            source: Dotted path into trace data, e.g. "trace.total_duration_ms".
            curve: Value curve to apply (default: Linear).
            agg: Aggregation method.
            weight: Relative weight in combined score.
            description: Human-readable description.
        """
        self._metrics.append(
            MetricDef(
                name=metric,
                source=source,
                curve=curve or Linear(min_threshold=0.0, max_perfect=1.0),
                agg=agg,
                weight=weight,
                description=description,
            )
        )
        return self

    def assume(self, **kwargs: Any) -> "ValueMapper":
        """Set assumptions used in value projection (e.g. volume, unit price)."""
        self._assumptions.update(kwargs)
        return self

    def calculate(
        self,
        trace: FlowTrace,
        *,
        volume: int | None = None,
        unit_price: float | None = None,
    ) -> ValueReport:
        """Calculate value from a single flow trace.

        Args:
            trace: The execution trace to analyze.
            volume: Optional monthly volume for projection.
            unit_price: Optional unit price per flow execution.

        Returns:
            A ValueReport with the full auditable calculation chain.
        """
        chain: list[CalcStep] = []
        breakdown: dict[str, float] = {}
        total_weight = sum(m.weight for m in self._metrics)
        combined = 0.0

        for m in self._metrics:
            # extract raw value from trace
            raw = self._extract(trace, m.source, m.agg)
            transformed = m.curve.evaluate(raw)
            weighted = transformed * (m.weight / total_weight) if total_weight > 0 else 0.0

            chain.append(
                CalcStep(
                    source=m.source,
                    samples=len(trace.steps),
                    filter=f"flow_name == '{trace.flow_name}'",
                    agg=m.agg,
                    raw_value=raw,
                    transform=m.curve.describe(),
                    transformed_value=transformed,
                )
            )
            breakdown[m.name] = weighted
            combined += weighted

        # project to period if volume given
        total_value = combined
        if volume is not None and unit_price is not None:
            total_value = combined * unit_price * (volume or 1)
            chain.append(
                CalcStep(
                    source="projection",
                    samples=1,
                    filter="",
                    agg="product",
                    raw_value=combined,
                    transform=f"combined * unit_price({unit_price}) * volume({volume})",
                    transformed_value=total_value,
                )
            )

        # sensitivity analysis
        sensitivity: dict[str, dict[str, str]] = {}
        if volume is not None:
            sensitivity["volume"] = {
                "+10%": f"${total_value * 1.10:.2f}",
                "-10%": f"${total_value * 0.90:.2f}",
            }
        if unit_price is not None:
            sensitivity["unit_price"] = {
                "+10%": f"${combined * unit_price * 1.10 * (volume or 1):.2f}",
                "-10%": f"${combined * unit_price * 0.90 * (volume or 1):.2f}",
            }

        return ValueReport(
            total_value=round(total_value, 2),
            confidence=round(self._confidence(trace), 2),
            chain=chain,
            breakdown=breakdown,
            sensitivity=sensitivity,
            assumptions=dict(self._assumptions),
        )

    # ── helpers ──

    def _extract(self, trace: FlowTrace, source: str, agg: str) -> float:
        """Extract and aggregate a value from the trace."""
        values: list[float] = []

        if source == "trace.total_duration_ms":
            values = [trace.total_duration_ms]
        elif source == "trace.success":
            values = [1.0 if trace.success else 0.0]
        elif ".output." in source:
            # e.g. "compose_reply.output.confidence"
            parts = source.split(".output.")
            action_name = parts[0]
            field = parts[1] if len(parts) > 1 else ""
            for s in trace.steps:
                if s.action_name == action_name and field in s.output:
                    raw = s.output[field]
                    if isinstance(raw, (int, float, bool)):
                        values.append(float(raw))
        elif ".duration_ms" in source:
            values = [s.duration_ms for s in trace.steps]

        if not values:
            return 0.0

        if agg == "mean":
            return sum(values) / len(values)
        elif agg == "sum":
            return sum(values)
        elif agg == "max":
            return max(values)
        elif agg == "min":
            return min(values)
        elif agg == "rate":
            return sum(1 for v in values if v > 0) / len(values)
        elif agg == "p95":
            sorted_vals = sorted(values)
            idx = int(len(sorted_vals) * 0.95)
            return sorted_vals[min(idx, len(sorted_vals) - 1)]
        else:
            return sum(values) / len(values)

    def _confidence(self, trace: FlowTrace) -> float:
        """Estimate confidence based on trace completeness and success rate."""
        if not trace.steps:
            return 0.0
        success_rate = sum(1 for s in trace.steps if s.success) / len(trace.steps)
        coverage = min(1.0, len(trace.steps) / 10)  # plateaus at 10 steps
        return 0.5 * success_rate + 0.5 * coverage
