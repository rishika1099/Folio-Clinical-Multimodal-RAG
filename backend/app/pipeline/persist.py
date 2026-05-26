"""
Persist an extracted report into MongoDB, scoped to a single user.

Every doc we write — the report itself, plus per-user master lists and
timeline series — carries `user_id` so reads can be partitioned with
compound indexes. The RAG index also carries user_id so chat retrieval
never crosses user boundaries.
"""
import asyncio

from ..db import get_db
from ..rag.store import index_report
from ..schemas import ExtractedReport


async def persist_report(report: ExtractedReport, user_id: str) -> None:
    db = get_db()
    doc = report.model_dump()
    doc["user_id"] = user_id

    coros = [db.reports.insert_one(doc)]

    for d in report.diagnoses:
        if d.condition:
            coros.append(db.diagnoses_master.update_one(
                {"user_id": user_id, "condition": d.condition.lower()},
                {"$set": {"user_id": user_id, "condition": d.condition.lower(),
                          "icd10": d.icd10, "status": d.status,
                          "last_seen": report.uploaded_at,
                          "confidence": d.confidence},
                 "$inc": {"occurrences": 1}},
                upsert=True,
            ))

    for m in report.medications:
        if m.name:
            coros.append(db.medications_master.update_one(
                {"user_id": user_id, "name": m.name.lower()},
                {"$set": {"user_id": user_id, "name": m.name.lower(),
                          "display_name": m.name,
                          "dose": m.dose, "frequency": m.frequency,
                          "purpose": m.purpose, "last_seen": report.uploaded_at,
                          "active": True},
                 "$inc": {"occurrences": 1}},
                upsert=True,
            ))

    for v in report.vitals:
        coros.append(db.vitals_timeline.insert_one({
            "user_id": user_id,
            "report_id": report.report_id,
            "type": v.type, "value": v.value, "unit": v.unit,
            "recorded_at": v.recorded_at or report.uploaded_at,
        }))

    for l in report.labs:
        coros.append(db.labs_timeline.insert_one({
            "user_id": user_id,
            "report_id": report.report_id,
            "test": l.test, "value": l.value, "unit": l.unit,
            "reference_range": l.reference_range, "flag": l.flag,
            "recorded_at": report.uploaded_at,
        }))

    async def _safe_index():
        try:
            await index_report(doc, user_id=user_id)
        except Exception as exc:
            print(f"[persist] embedding skipped: {exc}")

    coros.append(_safe_index())
    await asyncio.gather(*coros)
