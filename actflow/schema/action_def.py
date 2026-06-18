"""Action schema definition — the atomic unit of ActionFlow.

An ActionDef declares the input/output contract of an agent action.
It is framework-agnostic: the same ActionDef can be used with
LangChain, CrewAI, AutoGen, or raw Python.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SideEffectLevel(str, Enum):
    """Severity of side effects for dry-run / human-approval gating."""

    READ_ONLY = "read_only"
    INTERNAL = "internal"
    EXTERNAL_IDEMPOTENT = "idempotent"
    EXTERNAL_NON_IDEMPOTENT = "danger"
    DESTRUCTIVE = "destructive"


class ActionDef(BaseModel):
    """Declare the input/output contract of a single agent action.

    An ActionDef does NOT contain execution logic — it only describes
    what goes in and what comes out.  The actual execution is bound
    at runtime via `Runtime.bind()`.

    Example::

        search = ActionDef(
            name="search_kb",
            description="Search the knowledge base",
            input_schema={"query": str, "top_k": int},
            output_schema={"docs": list},
        )
    """

    name: str = Field(..., description="Unique action name within a domain")
    description: str = Field("", description="Human-readable description")
    domain: str = Field("default", description="Domain this action belongs to")
    version: str = Field("1.0.0", description="SemVer for schema evolution")

    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of field_name -> Python type (str, int, float, list, dict, ...)",
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of field_name -> Python type",
    )

    side_effects: list[str] = Field(
        default_factory=list,
        description="Human-readable labels for side effects, e.g. ['sends_email']",
    )
    side_effect_level: SideEffectLevel = Field(
        default=SideEffectLevel.READ_ONLY,
        description="Severity — used by Runtime to gate execution in dry-run / production",
    )

    requires_human_approval: bool = Field(
        default=False,
        description="If True, Runtime pauses and waits for a human approval token",
    )

    timeout_ms: int = Field(30000, description="Default timeout for this action")
    retry_policy: Optional[dict[str, Any]] = Field(
        default=None,
        description="e.g. {'max_retries': 3, 'backoff': 'exponential'}",
    )

    # ── cross-framework bridge ──
    def to_langchain_tool(self):
        """Return a LangChain-compatible tool description dict."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_crewai_tool(self):
        """Return a CrewAI-compatible tool description dict."""
        return self.to_langchain_tool()  # same shape for now

    def validate_input(self, data: dict[str, Any]) -> dict[str, Any]:
        """Check that *data* satisfies input_schema.  Returns the data unchanged
        on success; raises `TypeError` or `ValueError` on mismatch."""
        for field, expected_type in self.input_schema.items():
            if field not in data:
                raise ValueError(
                    f"Action '{self.name}': missing required input field '{field}'"
                )
            actual = data[field]
            if not isinstance(actual, expected_type):
                raise TypeError(
                    f"Action '{self.name}' input '{field}': "
                    f"expected {expected_type.__name__}, got {type(actual).__name__}"
                )
        return data

    def validate_output(self, data: dict[str, Any]) -> dict[str, Any]:
        """Check that *data* satisfies output_schema."""
        for field, expected_type in self.output_schema.items():
            if field not in data:
                raise ValueError(
                    f"Action '{self.name}': missing required output field '{field}'"
                )
            actual = data[field]
            if not isinstance(actual, expected_type):
                raise TypeError(
                    f"Action '{self.name}' output '{field}': "
                    f"expected {expected_type.__name__}, got {type(actual).__name__}"
                )
        return data
