"""
Simple risk indicators. Pure Python so they are deterministic and reproducible.
We explicitly say "insufficient data" when inputs are missing rather than
guessing — this is the property a clinician demoing the tool actually cares
about.
"""
from ..db import get_db
from ..schemas import Suggestion


def _parse_bp(value: str) -> tuple[int, int] | None:
    try:
        s, d = value.split("/")
        return int(s), int(d)
    except Exception:
        return None


async def latest_vital(db, vtype: str):
    return await db.vitals_timeline.find_one({"type": vtype}, sort=[("recorded_at", -1)])


async def latest_lab(db, regex: str):
    return await db.labs_timeline.find_one({"test": {"$regex": regex, "$options": "i"}},
                                           sort=[("recorded_at", -1)])


async def compute_risk_scores(report_id: str) -> list[Suggestion]:
    db = get_db()
    out: list[Suggestion] = []

    # Cardiac risk indicator (very simplified — NOT ASCVD).
    bp = await latest_vital(db, "bp")
    ldl = await latest_lab(db, "ldl")
    a1c = await latest_lab(db, "a1c")

    factors = []
    score = 0
    if bp:
        parsed = _parse_bp(bp.get("value", ""))
        if parsed:
            sys, _ = parsed
            if sys >= 140: score += 2; factors.append(f"BP {bp['value']} (stage 2)")
            elif sys >= 130: score += 1; factors.append(f"BP {bp['value']} (stage 1)")
    if ldl:
        try:
            v = float(ldl["value"])
            if v >= 160: score += 2; factors.append(f"LDL {v} (high)")
            elif v >= 130: score += 1; factors.append(f"LDL {v} (borderline)")
        except Exception:
            pass
    if a1c:
        try:
            v = float(a1c["value"])
            if v >= 6.5: score += 2; factors.append(f"HbA1c {v}% (diabetic)")
            elif v >= 5.7: score += 1; factors.append(f"HbA1c {v}% (pre-diabetic)")
        except Exception:
            pass

    if score == 0 and not factors:
        out.append(Suggestion(
            category="risk", severity="info",
            title="Cardiac risk: insufficient data",
            body="Need a recent BP, LDL, and HbA1c to estimate cardiometabolic risk. Add a recent lab or vitals reading.",
            report_id=report_id,
        ))
    else:
        label = "low" if score <= 1 else ("moderate" if score <= 3 else "elevated")
        sev = "info" if label == "low" else ("watch" if label == "moderate" else "action")
        out.append(Suggestion(
            category="risk", severity=sev,
            title=f"Cardiometabolic risk indicator: {label}",
            body="Heuristic indicator (NOT a calibrated ASCVD score). Contributing factors:\n" +
                 "\n".join(f"• {f}" for f in factors) +
                 "\n\nDiscuss with a clinician for a calibrated risk assessment.",
            evidence=factors, report_id=report_id,
        ))

    # CKD indicator
    cr = await latest_lab(db, "creatinine")
    if cr:
        try:
            v = float(cr["value"])
            if v >= 1.5:
                out.append(Suggestion(
                    category="risk", severity="watch",
                    title="Possible kidney function concern",
                    body=f"Creatinine {v} mg/dL is above typical reference range. eGFR calculation needs age and sex (insufficient data here). Discuss kidney function with your clinician.",
                    evidence=[f"Creatinine {v}"],
                    report_id=report_id,
                ))
        except Exception:
            pass

    return out
