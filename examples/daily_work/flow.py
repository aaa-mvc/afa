"""Daily Work: 早上 9 点，打开电脑，跑这个。

场景：昨晚 GitHub 上 star 了 3 个仓库，今天早上想快速判断哪个值得深读。
"""

from actflow import ActionDef, Flow, Runtime, ValueMapper
from actflow.value.curves import Linear


# ── Action 1: 从 GitHub 拿到昨天的 starred 仓库 ──
fetch_stars = ActionDef(
    name="fetch_stars",
    description="Fetch yesterday's starred repos from GitHub",
    input_schema={"date": str},
    output_schema={"repos": list},  # [{name, description, stars, language}]
)

# ── Action 2: 对每个仓库做快速判断 ──
score_repos = ActionDef(
    name="score_repos",
    description="Score each repo on relevance, quality, and learning value",
    input_schema={"repos": list},
    output_schema={"ranked": list, "top_pick": str, "verdict": str},
)

# ── Action 3: 把结果写到 Obsidian 日记 ──
write_to_obsidian = ActionDef(
    name="write_to_obsidian",
    description="Write the daily repo digest to Obsidian daily note",
    input_schema={"top_pick": str, "verdict": str, "ranked": list},
    output_schema={"written": bool, "file_path": str},
    side_effect_level="internal",
)


# ── Flow ──
flow = (
    Flow("daily_repo_triage", version="1.0.0")
    .step(fetch_stars)
    .step(score_repos, depends_on=["fetch_stars"])
    .step(write_to_obsidian, depends_on=["score_repos"])
)


# ── Mock 实现（用自己的逻辑替换，或接 DeepSeek）──

def fetch_stars(date: str) -> dict:
    """Mock：假装从 GitHub API 拉到了昨天的 star。"""
    return {
        "repos": [
            {"name": "microsoft/autogen", "description": "Multi-agent conversation framework", "stars": 48000, "language": "Python"},
            {"name": "BerriAI/litellm", "description": "Call 100+ LLM APIs in OpenAI format", "stars": 22000, "language": "Python"},
            {"name": "run-llama/llama_index", "description": "Data framework for LLM applications", "stars": 41000, "language": "Python"},
        ]
    }


def score_repos(repos: list) -> dict:
    """Mock：假装用 LLM 打了分。

    真实场景：这里接 DeepSeek，prompt 是：
    "你是一个技术选型顾问。对以下 3 个仓库打分（0-100），
     维度：与我技术栈的匹配度、社区活跃度、学习价值。
     只回复 JSON。"
    """
    scored = []
    for r in repos:
        score = 85 if "autogen" in r["name"] else (78 if "litellm" in r["name"] else 72)
        scored.append({**r, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[0]

    return {
        "ranked": scored,
        "top_pick": f"{top['name']} ({top['score']}/100)",
        "verdict": f"今天深读 {top['name']}。自动化的 Agent 框架正好匹配当前 AFA 项目方向。litellm 作为备选，未来做多模型路由时查阅。",
    }


def write_to_obsidian(top_pick: str, verdict: str, ranked: list) -> dict:
    """Mock：假装写入了 Obsidian 日记。"""
    return {
        "written": True,
        "file_path": f"G:/Obsidian/daily/2026-06-18.md",
    }


# ── 如果直接跑这个文件 ──
if __name__ == "__main__":
    runtime = Runtime(flow)
    runtime.bind_all(
        fetch_stars=fetch_stars,
        score_repos=score_repos,
        write_to_obsidian=write_to_obsidian,
    )

    result = runtime.run({"date": "2026-06-17"})
    print(f"Status: {result.status}  |  Steps: {len(result.trace.steps)}")
    for s in result.trace.steps:
        icon = "OK" if s.success else "FAIL"
        print(f"  [{icon}] {s.step_name}")
        if s.success and s.output:
            for k, v in s.output.items():
                val = str(v)[:80]
                print(f"         {k}: {val}")

    report = (
        ValueMapper(flow)
        .map(metric="quality", source="score_repos.output.ranked",
             curve=Linear(min_threshold=0, max_perfect=100))
        .calculate(result.trace)
    )
    print(f"\nValue: {report.total_value:.2f}")
