"""
Differential diagnosis suggestions. Quality > latency, so we use the
strongest reasoning model. Always returned with an "exploratory, not
diagnostic" caveat baked into the prompt.
"""
import json

from ..config import settings
from ..db import get_db
from ..models.router import ROUTE_REASON_FALLBACK, ROUTE_REASON_PRIMARY, complete_json
from ..schemas import Suggestion


SYSTEM = """You are a careful clinical educator. Given a patient's recent symptoms, vitals, labs, and active diagnoses, list up to 4 plausible differential diagnoses ranked by likelihood. This is for educational exploration, NOT diagnosis.

Output JSON only:
{
  "differentials": [
    {"condition": "", "likelihood": "high|moderate|low", "rationale": "", "would_evaluate_with": ""}
  ]
}

Be conservative. Do not list extremely rare conditions unless evidence strongly supports them. If evidence is too thin, return {"differentials": []}.
"""


async def generate_differentials(report_id: str, user_id: str) -> list[Suggestion]:
    db = get_db()
    report = await db.reports.find_one({"user_id": user_id, "report_id": report_id})
    if not report:
        return []

    symptoms = report.get("symptoms", [])
    if not symptoms:
        return []

    active_dx = await db.diagnoses_master.find(
        {"user_id": user_id, "status": "active"}
    ).to_list(length=20)

    user = json.dumps({
        "current_symptoms": symptoms,
        "current_vitals": report.get("vitals", []),
        "current_labs": report.get("labs", []),
        "active_diagnoses": [d["condition"] for d in active_dx],
    })

    if not (settings.anthropic_api_key or settings.openai_api_key):
        return []

    try:
        result = await complete_json(SYSTEM, user, ROUTE_REASON_PRIMARY, ROUTE_REASON_FALLBACK,
                                      max_tokens=800, timeout_s=settings.suggestion_timeout_s)
    except Exception:
        return []

    diffs = result.get("differentials", [])
    if not diffs:
        return []
    body_lines = []
    for d in diffs[:4]:
        body_lines.append(f"• {d.get('condition','?')} ({d.get('likelihood','?')}) — {d.get('rationale','')}".strip())
    body_lines.append("")
    body_lines.append("Exploratory only. Not a diagnosis. Discuss any concerns with a clinician.")
    return [Suggestion(
        category="differential", severity="info",
        title="Possible differentials to discuss",
        body="\n".join(body_lines),
        evidence=[s.get("description", "") for s in symptoms],
        report_id=report_id,
    )]
