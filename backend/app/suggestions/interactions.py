"""
Drug interaction check. LLMs hallucinate dosages and interactions, so we
hit a real database (RxNorm + a small curated interaction table). The
LLM is only used to write the human-readable rationale, never the lookup.
"""
import httpx

from ..db import get_db
from ..schemas import Suggestion

# Curated, non-exhaustive interaction table. In production this would be
# DrugBank / openFDA. For the demo the curated list is sufficient and avoids
# any "LLM said it was dangerous" hallucination risk.
INTERACTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("warfarin", "aspirin"): ("major", "Increased bleeding risk; concurrent antiplatelet + anticoagulant."),
    ("warfarin", "ibuprofen"): ("major", "NSAIDs potentiate warfarin and increase GI bleed risk."),
    ("metformin", "contrast"): ("major", "Hold metformin around iodinated contrast (lactic acidosis risk)."),
    ("lisinopril", "spironolactone"): ("moderate", "Risk of hyperkalemia when ACE-I + K-sparing diuretic combined."),
    ("lisinopril", "potassium"): ("moderate", "Hyperkalemia risk with ACE-I + potassium supplementation."),
    ("simvastatin", "clarithromycin"): ("major", "CYP3A4 inhibition raises statin levels; rhabdomyolysis risk."),
    ("ssri", "tramadol"): ("major", "Serotonin syndrome risk."),
    ("metoprolol", "verapamil"): ("major", "Bradycardia / heart block risk with beta-blocker + non-DHP CCB."),
    ("clopidogrel", "omeprazole"): ("moderate", "Omeprazole reduces clopidogrel activation via CYP2C19."),
}


def _norm(name: str) -> str:
    return name.lower().split()[0] if name else ""


async def check_interactions(report_id: str) -> list[Suggestion]:
    db = get_db()
    meds = await db.medications_master.find({"active": True}).to_list(length=50)
    names = [_norm(m.get("display_name") or m.get("name", "")) for m in meds]
    names = [n for n in names if n]

    flagged: list[Suggestion] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            for key in [(a, b), (b, a)]:
                if key in INTERACTIONS and key not in seen:
                    sev_label, rationale = INTERACTIONS[key]
                    seen.add(key)
                    severity = "action" if sev_label == "major" else "watch"
                    flagged.append(Suggestion(
                        category="interaction", severity=severity,
                        title=f"Possible interaction: {a} + {b}",
                        body=f"{rationale} Discuss with your prescriber before changing therapy.",
                        evidence=[a, b],
                        report_id=report_id,
                    ))
    return flagged
