"""Vital-trend detection. Pure Python; LLM only writes the natural-language summary."""
from ..db import get_db
from ..schemas import Suggestion


def _parse_bp(value: str) -> tuple[int, int] | None:
    try:
        s, d = value.split("/")
        return int(s), int(d)
    except Exception:
        return None


async def detect_trends(report_id: str, user_id: str) -> list[Suggestion]:
    db = get_db()
    out: list[Suggestion] = []

    bps = await db.vitals_timeline.find(
        {"user_id": user_id, "type": "bp"}
    ).sort("recorded_at", -1).to_list(length=5)
    parsed = [(_parse_bp(b["value"]), b) for b in bps]
    parsed = [(p, b) for p, b in parsed if p]
    if len(parsed) >= 3:
        sys_vals = [p[0][0] for p, _ in parsed][:3][::-1]
        if sys_vals[-1] - sys_vals[0] >= 10 and sys_vals[0] < sys_vals[1] < sys_vals[2]:
            out.append(Suggestion(
                category="trend", severity="watch",
                title="Blood pressure trending up",
                body=f"Systolic BP has trended up across your last 3 readings: {sys_vals[0]} → {sys_vals[1]} → {sys_vals[2]} mmHg. Consider home monitoring and a clinician follow-up if this persists.",
                evidence=[f"BP {sys_vals[0]}", f"BP {sys_vals[1]}", f"BP {sys_vals[2]}"],
                report_id=report_id,
            ))

    a1cs = await db.labs_timeline.find(
        {"user_id": user_id, "test": {"$regex": "a1c", "$options": "i"}}
    ).sort("recorded_at", -1).to_list(length=5)
    if len(a1cs) >= 2:
        try:
            recent = float(a1cs[0]["value"])
            prior = float(a1cs[1]["value"])
            if recent - prior >= 0.3:
                out.append(Suggestion(
                    category="trend", severity="watch",
                    title="HbA1c rising",
                    body=f"HbA1c has risen from {prior}% to {recent}%. A change of ≥0.3% can warrant therapy adjustment per ADA.",
                    evidence=[f"HbA1c {prior}%", f"HbA1c {recent}%"],
                    report_id=report_id,
                ))
        except Exception:
            pass

    return out
