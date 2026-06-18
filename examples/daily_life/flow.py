"""Daily Life: 早上出门前跑这个。查天气 + 日程 + 评论 -> 早间简报。"""

from actflow import ActionDef, Flow, Runtime, ValueMapper
from actflow.value.curves import ExponentialDecay

check_weather = ActionDef(name="check_weather", input_schema={"city": str},
    output_schema={"temp_c": int, "condition": str, "need_umbrella": bool})
check_calendar = ActionDef(name="check_calendar", input_schema={"date": str},
    output_schema={"events": list, "has_conflict": bool, "first_event_time": str})
check_youtube = ActionDef(name="check_youtube", input_schema={"channel_id": str},
    output_schema={"new_comments": int, "top_comment": str, "needs_reply": bool})
generate_briefing = ActionDef(name="generate_briefing",
    input_schema={"weather": dict, "calendar": dict, "youtube": dict},
    output_schema={"briefing_text": str, "actions_today": list})

flow = (Flow("morning_briefing")
    .step(check_weather).step(check_calendar).step(check_youtube)
    .step(generate_briefing, depends_on=["check_weather", "check_calendar", "check_youtube"]))

def check_weather(city): return {"temp_c": 28, "condition": "cloudy then rain", "need_umbrella": True}
def check_calendar(date): return {"events": [{"time": "10:00", "title": "AFA review"}, {"time": "15:00", "title": "Client demo"}], "has_conflict": False, "first_event_time": "10:00"}
def check_youtube(channel_id): return {"new_comments": 3, "top_comment": "LabVLA episode was amazing. Can you make one on ActionFlow?", "needs_reply": True}
def generate_briefing(weather, calendar, youtube):
    lines = ["Morning Briefing | 2026-06-18", "", f"Weather: {weather['temp_c']}C, {weather['condition']}"]
    if weather["need_umbrella"]: lines.append("  -> Take umbrella!")
    lines.append(f"Calendar: {len(calendar['events'])} events, first at {calendar['first_event_time']}")
    if youtube["needs_reply"]: lines.append(f"YouTube: {youtube['new_comments']} new comments. Top: {youtube['top_comment'][:60]}...")
    actions = []
    if weather["need_umbrella"]: actions.append("Take umbrella")
    if calendar["first_event_time"] == "10:00": actions.append("Prep review materials by 9:45")
    if youtube["needs_reply"]: actions.append("Reply to YouTube comments at lunch")
    return {"briefing_text": "\n".join(lines), "actions_today": actions}

if __name__ == "__main__":
    runtime = Runtime(flow)
    runtime.bind_all(check_weather=check_weather, check_calendar=check_calendar,
                     check_youtube=check_youtube, generate_briefing=generate_briefing)
    result = runtime.run({"city": "Hangzhou", "date": "2026-06-18", "channel_id": "@ai-channel"})
    print(f"Status: {result.status} | Steps: {len(result.trace.steps)}")
    for s in result.trace.steps: print(f"  [{'OK' if s.success else 'FAIL'}] {s.step_name}")
    print("\n" + result.state.get("generate_briefing.output.briefing_text", ""))
    actions = result.state.get("generate_briefing.output.actions_today", [])
    print("\nToday:")
    for a in actions: print(f"  - {a}")
    report = ValueMapper(flow).map(metric="speed", source="trace.total_duration_ms",
        curve=ExponentialDecay(perfect=500, half_life=5000)).calculate(result.trace)
    print(f"\nValue: {report.total_value:.2f}")
