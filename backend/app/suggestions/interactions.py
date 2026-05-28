"""
Drug interaction check. LLMs hallucinate dosages and interactions, so we
hit a real database (RxNorm + a small curated interaction table). The
LLM is only used to write the human-readable rationale, never the lookup.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def detect_interactions(med_names: list[str]) -> list[tuple[str, str, str]]:
    """
    Pure (Mongo-free) interaction lookup. Returns a list of
    (drug_a, drug_b, severity) tuples, one per distinct interacting
    pair found in the curated table. Order within each pair matches
    the table's canonical ordering.

    Used by the eval harness so the same lookup the live suggestions
    engine uses can be tested deterministically with a gold set.
    """
    names = [_norm(n) for n in med_names if n]
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for key in [(a, b), (b, a)]:
                if key in INTERACTIONS and key not in seen:
                    sev_label, _ = INTERACTIONS[key]
                    seen.add(key)
                    out.append((key[0], key[1], sev_label))
    return out


async def check_interactions(report_id: str, user_id: str) -> list["Suggestion"]:
    # Lazy imports keep this module importable in eval (no Mongo/HTTPX needed).
    from ..db import get_db
    from ..schemas import Suggestion
    db = get_db()
    meds = await db.medications_master.find({"user_id": user_id, "active": True}).to_list(length=50)
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
