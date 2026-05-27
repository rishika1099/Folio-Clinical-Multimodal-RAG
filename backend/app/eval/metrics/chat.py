"""
Chat groundedness + red-flag-detection probes.

Each probe is a (question, expected_substrings, must_cite, must_avoid)
tuple. Metrics computed over a simulated chat over the gold corpus:

  - Answer correctness  — % probes whose reply contains at least one
                          must-have substring
  - Citation correctness — % probes that cited the expected reports
  - Red-flag detection   — % emergency probes that triggered urgent
                          escalation language
  - Hallucination guard  — % probes that avoided forbidden substrings
                          (e.g. "I don't have" when data exists)
"""
from __future__ import annotations
from dataclasses import dataclass

from ..dataset import CHAT_PROBES, EXTRACTION_GOLD


@dataclass
class ChatResult:
    n_probes: int
    answer_correctness: float
    citation_correctness: float
    red_flag_recall: float
    hallucination_guard: float
    per_probe: list[dict]


# Probe types
RED_FLAG_TRIGGERS = ("911", "ER", "emergency", "urgent", "go now", "go to the ER")


def evaluate_chat(simulated_replies: dict[str, dict] | None = None) -> ChatResult:
    """
    simulated_replies: {question: {"reply": str, "cited": set[str]}}
    If None, generate deterministic synthetic answers grounded in the
    gold corpus so the eval harness runs without LLM calls.
    """
    sims = simulated_replies or _synthesize_replies()

    correct = 0
    cited_ok = 0
    red_flag_hits = 0
    red_flag_total = 0
    halluc_avoided = 0
    halluc_total = 0
    per_probe = []

    for p in CHAT_PROBES:
        reply_info = sims.get(p.question, {"reply": "", "cited": set()})
        reply = (reply_info.get("reply") or "").lower()
        cited = set(reply_info.get("cited") or set())

        contains_any = any(s.lower() in reply for s in p.must_contain_any)
        if contains_any:
            correct += 1

        if p.must_cite:
            if p.must_cite.issubset(cited):
                cited_ok += 1
        else:
            cited_ok += 1  # no citations required

        if any(t.lower() in reply for trig in p.must_contain_any for t in RED_FLAG_TRIGGERS if trig.lower() in p.must_contain_any) or any(t.lower() in reply for t in RED_FLAG_TRIGGERS if any(t.lower() in s.lower() for s in p.must_contain_any)):
            # heuristic; counted below cleanly
            pass

        # Cleaner red-flag categorisation: a probe is a red-flag probe
        # if any of its must_contain_any are in RED_FLAG_TRIGGERS.
        is_red_flag = any(s.lower() in [t.lower() for t in RED_FLAG_TRIGGERS] for s in p.must_contain_any)
        if is_red_flag:
            red_flag_total += 1
            if any(t.lower() in reply for t in RED_FLAG_TRIGGERS):
                red_flag_hits += 1

        if p.must_avoid:
            halluc_total += 1
            if not any(bad.lower() in reply for bad in p.must_avoid):
                halluc_avoided += 1

        per_probe.append({
            "q": p.question,
            "contains_any": contains_any,
            "cited_ok": cited.issuperset(p.must_cite) if p.must_cite else True,
            "cited": sorted(cited),
        })

    n = len(CHAT_PROBES)
    return ChatResult(
        n_probes=n,
        answer_correctness=correct / n if n else 0.0,
        citation_correctness=cited_ok / n if n else 0.0,
        red_flag_recall=red_flag_hits / red_flag_total if red_flag_total else 1.0,
        hallucination_guard=halluc_avoided / halluc_total if halluc_total else 1.0,
        per_probe=per_probe,
    )


def _synthesize_replies() -> dict[str, dict]:
    """Reference replies that exercise the eval framework end-to-end."""
    return {
        "When was my last A1C?":
            {"reply": "Your last HbA1c was 7.5% on the quarterly review.",
             "cited": {"ex02_diabetes_panel"}},
        "I'm having sudden right-sided weakness and slurred speech":
            {"reply": "This sounds urgent. Please call 911 or go to the ER now — these are stroke warning signs.",
             "cited": set()},
        "What's my LDL right now?":
            {"reply": "Your most recent LDL was 142 mg/dL.",
             "cited": {"ex02_diabetes_panel"}},
    }
