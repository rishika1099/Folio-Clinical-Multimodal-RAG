"""
Persist an extracted report into MongoDB. Fans out master-list upserts
in parallel via asyncio.gather so the only sequential bottleneck is the
LLM extraction itself.

After persistence we also kick off an embedding for the RAG index so
chat retrieval has fresh context. Embedding is awaited inside the same
gather call — it's <100ms with the OpenAI API.
"""
import asyncio

from ..db import get_db
from ..schemas import ExtractedReport
from ..rag.store import index_report


async def persist_report(report: ExtractedReport) -> None:
    db = get_db()
    doc = report.model_dump()

    coros = [db.reports.insert_one(doc)]

    for d in report.diagnoses:
        if d.condition:
            coros.append(db.diagnoses_master.update_one(
                {"condition": d.condition.lower()},
                {"$set": {"condition": d.condition.lower(), "icd10": d.icd10,
                          "status": d.status, "last_seen": report.uploaded_at,
                          "confidence": d.confidence},
                 "$inc": {"occurrences": 1}},
                upsert=True,
            ))

    for m in report.medications:
        if m.name:
            coros.append(db.medications_master.update_one(
                {"name": m.name.lower()},
                {"$set": {"name": m.name.lower(), "display_name": m.name,
                          "dose": m.dose, "frequency": m.frequency,
                          "purpose": m.purpose, "last_seen": report.uploaded_at,
                          "active": True},
                 "$inc": {"occurrences": 1}},
                upsert=True,
            ))

    for v in report.vitals:
        coros.append(db.vitals_timeline.insert_one({
            "report_id": report.report_id,
            "type": v.type, "value": v.value, "unit": v.unit,
            "recorded_at": v.recorded_at or report.uploaded_at,
        }))

    for l in report.labs:
        coros.append(db.labs_timeline.insert_one({
            "report_id": report.report_id,
            "test": l.test, "value": l.value, "unit": l.unit,
            "reference_range": l.reference_range, "flag": l.flag,
            "recorded_at": report.uploaded_at,
        }))

    # Embed for RAG retrieval. Best-effort — never block persistence.
    async def _safe_index():
        try:
            await index_report(doc)
        except Exception as exc:
            print(f"[persist] embedding skipped: {exc}")

    coros.append(_safe_index())
    await asyncio.gather(*coros)
