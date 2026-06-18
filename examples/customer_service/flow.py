"""Example: Customer Inquiry Flow.

Usage:
    actflow test examples/customer_service/flow.py
    actflow run examples/customer_service/flow.py
    actflow visualize examples/customer_service/flow.py
"""

from actflow import ActionDef, Flow, Runtime, ValueMapper
from actflow.value.curves import ExponentialDecay, Linear

# ── Action Definitions ──

search_kb_def = ActionDef(
    name="search_kb",
    description="Search the knowledge base for relevant documents",
    domain="customer_service",
    version="1.0.0",
    input_schema={"query": str},
    output_schema={"docs": list},
)

compose_reply_def = ActionDef(
    name="compose_reply",
    description="Compose a reply using retrieved documents",
    domain="customer_service",
    version="1.0.0",
    input_schema={"docs": list, "tone": str},
    output_schema={"draft": str, "confidence": float},
)

send_email_def = ActionDef(
    name="send_email",
    description="Send the composed reply to the customer",
    domain="customer_service",
    version="1.0.0",
    input_schema={"to": str, "body": str},
    output_schema={"sent": bool},
    side_effect_level="idempotent",
)

# ── Flow ──

flow = (
    Flow("customer_inquiry", version="1.0.0")
    .step(search_kb_def)
    .step(compose_reply_def, depends_on=["search_kb"])
    .step(send_email_def, depends_on=["compose_reply"])
    # Note: do NOT call .compile() here — CLI does it, or call it explicitly at runtime.
)

# ── Implementations (for `actflow run`) ──


def search_kb(query: str) -> dict:
    """Mock knowledge base search."""
    return {
        "docs": [
            "Return Policy: 30-day return, free shipping.",
            "Shipping FAQ: 3-5 business days standard.",
        ]
    }


def compose_reply(docs: list, tone: str) -> dict:
    """Mock reply composition."""
    return {
        "draft": f"Dear customer, based on our records: {docs[0]}. We hope this helps!",
        "confidence": 0.87,
    }


def send_email(to: str, body: str) -> dict:
    """Mock email sending."""
    return {"sent": True}


# ── Standalone run ──

if __name__ == "__main__":
    runtime = Runtime(flow)
    runtime.bind_all(
        search_kb=search_kb,
        compose_reply=compose_reply,
        send_email=send_email,
    )

    result = runtime.run({"query": "退货政策", "tone": "formal"})
    print(f"Status: {result.status}")
    print(f"Steps: {len(result.trace.steps)}")
    for s in result.trace.steps:
        print(f"  {'✅' if s.success else '❌'} {s.step_name} ({s.duration_ms:.0f}ms)")

    # Value report
    report = (
        ValueMapper(flow)
        .map(
            metric="response_time",
            source="trace.total_duration_ms",
            curve=ExponentialDecay(perfect=60000, half_life=300000),
        )
        .map(
            metric="quality",
            source="compose_reply.output.confidence",
            curve=Linear(min_threshold=0.7, max_perfect=1.0),
        )
        .calculate(result.trace)
    )
    print(report)
