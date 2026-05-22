"""Lifestyle / diet suggestions tied to active conditions. Cheap fast model."""
from ..config import settings
from ..db import get_db
from ..models.router import ROUTE_SUMMARIZE_FALLBACK, ROUTE_SUMMARIZE_PRIMARY, complete_text
from ..schemas import Suggestion


CANNED = {
    "hypertension": ("Try a low-sodium DASH-style diet",
        "DASH (Dietary Approaches to Stop Hypertension) emphasizes vegetables, fruits, whole grains, and low-fat dairy with sodium ≤2.3 g/day. Pair with 150 min/wk moderate aerobic activity. Discuss specific targets with your clinician."),
    "type 2 diabetes mellitus": ("Carbohydrate-aware eating pattern",
        "Focus on non-starchy vegetables, lean protein, and high-fiber carbs. Plate method (½ veg, ¼ protein, ¼ starch) is a simple anchor. Avoid sugar-sweetened beverages."),
    "hyperlipidemia": ("Mediterranean dietary pattern",
        "Emphasize olive oil, fish 2x/wk, nuts, legumes, whole grains; limit red and processed meat. Combined with regular activity, can lower LDL ~5-10%."),
    "ckd": ("Kidney-protective diet",
        "Moderate protein (~0.8 g/kg/day), low sodium, watch potassium and phosphorus per labs. Stay well-hydrated unless fluid-restricted."),
}


async def generate_lifestyle(report_id: str) -> list[Suggestion]:
    db = get_db()
    actives = await db.diagnoses_master.find({"status": "active"}).to_list(length=10)
    out: list[Suggestion] = []

    for d in actives:
        cond = d.get("condition", "").lower()
        for key, (title, body) in CANNED.items():
            if key in cond:
                out.append(Suggestion(
                    category="lifestyle", severity="info",
                    title=title, body=body,
                    evidence=[d.get("condition", "")],
                    report_id=report_id,
                ))
                break

    return out
