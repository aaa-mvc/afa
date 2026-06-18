# ActionFlow — AI Agent 的"记账本"

**工作流追踪与价值计算。** 评估你的 Agent 做了什么、做的好吗 → 自动校验 → 追踪每一步 → 生成价值报告。知道 Agent 帮你省了多少、创造了多少价值。

*AI Agent's "ledger" for workflow tracking and value calculation. Evaluate what your agent has done and how well it has done ➡️ Automatically verify ➡️ Track every step ➡️ Generate value reports. Know how much money the agent has helped you earn.*

---

## 5 分钟跑起来

```bash
pip install actflow
```

```python
from actflow import ActionDef, Flow, Runtime, ValueMapper

# 1. 定义你的 Agent 做什么
search = ActionDef(name="search_kb", input_schema={"query": str}, output_schema={"docs": list})
compose = ActionDef(name="compose_reply", input_schema={"docs": list, "tone": str}, output_schema={"draft": str, "confidence": float})
send = ActionDef(name="send_email", input_schema={"to": str, "body": str}, output_schema={"sent": bool})

# 2. 串成流程
flow = (Flow("customer_inquiry")
    .step(search).step(compose, depends_on=["search"]).step(send, depends_on=["compose"]))

# 3. 绑定你的实现（或接 DeepSeek/Claude/GPT）
def search_kb(query): return {"docs": ["policy-doc-1", "policy-doc-2"]}
def compose_reply(docs, tone): return {"draft": f"Based on {len(docs)} docs...", "confidence": 0.87}
def send_email(to, body): return {"sent": True}

# 4. 跑一次，看价值
runtime = Runtime(flow)
runtime.bind_all(search_kb=search_kb, compose_reply=compose_reply, send_email=send_email)
result = runtime.run({"query": "退货政策", "tone": "formal"})
print(f"Steps: {len(result.trace.steps)}, Value: {ValueMapper(flow).calculate(result.trace).total_value:.2f}")
```

---

## 三个命令

```bash
actflow test flow.py      # 检查流程有没有漏洞
actflow run flow.py       # 跑一次，看每一步的追踪
actflow visualize flow.py # 画出流程图
```

---

## 示例

```bash
cd examples
python daily_work/flow.py   # 早间工作：GitHub star → 评分 → Obsidian
python daily_life/flow.py   # 早间生活：天气+日程+评论 → 简报
python customer_service/flow.py  # 客服：搜索→回复→发邮件
```

---

## 为什么需要 ActionFlow

AI Agent 越来越多了。但你问问自己：**你的 Agent 到底帮你省了多少、创造了多少价值？**

现在的 Agent 框架（LangChain、CrewAI、AutoGen）帮你调 LLM。但调完之后——每一步对不对、流程通不通、值多少钱——没人管。

**ActionFlow 不管 LLM 调用。它管 LLM 调完之后的事。**

---

## 安装

```bash
pip install actflow
```

---

MIT License
