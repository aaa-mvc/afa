# ActionFlow — Stateful Agent Action Runtime

**OpenAPI for Agent Actions + Airflow for Agent Workflows + Stripe for Agent Value Tracking**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## What is ActionFlow?

ActionFlow is a **stateful runtime** for agent actions. It fills the vacuum between LLM-calling frameworks (LangChain, CrewAI, AutoGen) and communication protocols (MCP, HTTP, WebSocket).

It does four things:

| Module | What | Analogy |
|--------|------|---------|
| **ActionSchema** | Declare the input/output contract of an agent action | OpenAPI for Actions |
| **Flow Compiler** | Compile actions into a validated DAG | Airflow for Agents |
| **Runtime** | Execute flows, track state, produce traces | Docker Runtime |
| **ValueMapper** | Translate execution traces into business value | Stripe for Value |

---

## 5-Minute Quick Start

```bash
pip install actflow
```

```python
from actflow import ActionDef, Flow, Runtime, ValueMapper
from actflow.value.curves import ExponentialDecay

# 1. Define 3 actions
search = ActionDef(
    name="search_kb",
    input_schema={"query": str},
    output_schema={"docs": list},
)

compose = ActionDef(
    name="compose_reply",
    input_schema={"docs": list, "tone": str},
    output_schema={"draft": str, "confidence": float},
)

send = ActionDef(
    name="send_email",
    input_schema={"to": str, "body": str},
    output_schema={"sent": bool},
    side_effect_level="idempotent",
)

# 2. Build a flow
flow = (
    Flow("customer_inquiry")
    .step(search)
    .step(compose, depends_on=["search"])
    .step(send, depends_on=["compose"])
    .compile()
)

# 3. Bind real functions
def search_kb(query):
    return {"docs": ["policy-doc-1", "policy-doc-2"]}

def compose_reply(docs, tone):
    return {"draft": f"Based on {len(docs)} docs, here is a {tone} reply...", "confidence": 0.87}

def send_email(to, body):
    return {"sent": True}

# 4. Run
runtime = Runtime(flow)
runtime.bind_all(search_kb=search_kb, compose_reply=compose_reply, send_email=send_email)
result = runtime.run({"query": "退货政策", "tone": "formal"})

# 5. Value report
report = (
    ValueMapper(flow)
    .map(metric="response_time", source="trace.total_duration_ms",
         curve=ExponentialDecay(perfect=60000, half_life=300000))
    .calculate(result.trace)
)
print(report)
# → ValueReport(total_value=0.94, confidence=0.83, ...)
```

---

## CLI

```bash
# Validate a flow
actflow test flow.py

# Run a flow (dry-run by default)
actflow run flow.py

# Run in live mode
actflow run flow.py --live

# Generate Mermaid diagram
actflow visualize flow.py
```

---

## Design Philosophy

- **Action-first, not State-first** — Define what actions do; state emerges from the action network
- **Framework-agnostic** — Same ActionDef works with LangChain, CrewAI, AutoGen, or raw Python
- **Compile-time safety** — Schema mismatches caught before execution
- **Auditable value** — Every value number has a traceable calculation chain

---

## Installation

```bash
pip install actflow
```

For development:

```bash
git clone https://github.com/YOUR_USERNAME/actflow.git
cd actflow
pip install -e ".[dev]"
```

---

## License

MIT — see [LICENSE](LICENSE).

---

*Inspired by LabVLA's DatasetSchema — the first proof that action schemas can drive an entire system.*
