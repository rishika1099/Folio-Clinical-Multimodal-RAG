"""
Cold-path orchestration. Runs all six suggestion generators in parallel
after the user already has their extraction. Writes per-user suggestions
into Mongo (every doc carries user_id).
"""
import asyncio

from ..db import get_db
from ..schemas import Suggestion
from . import differentials, followups, interactions, lifestyle, risk_scores, trends


CATEGORIES = (
    ("trend",        trends.detect_trends),
    ("interaction",  interactions.check_interactions),
    ("followup",     followups.generate_followups),
    ("lifestyle",    lifestyle.generate_lifestyle),
    ("risk",         risk_scores.compute_risk_scores),
    ("differential", differentials.generate_differentials),
)


async def _safe_run(name, fn, report_id, user_id):
    try:
        return await fn(report_id, user_id=user_id)
    except Exception as exc:
        print(f"[suggestions:{name}] failed: {exc}")
        return []


async def run_all(report_id: str, user_id: str) -> list[Suggestion]:
    results = await asyncio.gather(
        *[_safe_run(n, f, report_id, user_id) for n, f in CATEGORIES]
    )
    flat: list[Suggestion] = [s for group in results for s in group]
    if flat:
        db = get_db()
        await db.suggestions.insert_many(
            [{**s.model_dump(), "user_id": user_id} for s in flat]
        )
    return flat
