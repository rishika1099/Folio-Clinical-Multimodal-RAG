"""
Follow-up reminders. Rules are deterministic (guideline-based); the LLM
only phrases the reminder if needed.
"""
from datetime import datetime, timedelta

from ..db import get_db
from ..schemas import Suggestion


GUIDELINE_RECHECK_DAYS = {
    "a1c": 90,
    "ldl": 365,
    "tsh": 365,
    "creatinine": 180,
    "bp": 30,
}


async def generate_followups(report_id: str, user_id: str) -> list[Suggestion]:
    db = get_db()
    now = datetime.utcnow()
    out: list[Suggestion] = []

    for test, days in GUIDELINE_RECHECK_DAYS.items():
        last = await db.labs_timeline.find_one(
            {"user_id": user_id, "test": {"$regex": test, "$options": "i"}},
            sort=[("recorded_at", -1)],
        )
        if not last:
            continue
        try:
            last_dt = datetime.fromisoformat(str(last.get("recorded_at", "")).replace("Z", ""))
        except Exception:
            continue
        due = last_dt + timedelta(days=days)
        if due < now + timedelta(days=14):  # due now or within 2 weeks
            test_label = last["test"]
            out.append(Suggestion(
                category="followup",
                severity="info" if due > now else "watch",
                title=f"Recheck due: {test_label}",
                body=f"Last {test_label} was {last_dt.date().isoformat()} ({last['value']}{(' ' + last['unit']) if last.get('unit') else ''}). Routine recheck guideline interval is ~{days} days.",
                evidence=[f"{test_label} on {last_dt.date().isoformat()}"],
                report_id=report_id,
            ))
    return out
