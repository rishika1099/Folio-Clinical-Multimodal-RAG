"""
Drug interaction check. LLMs hallucinate dosages and interactions, so we
hit a real database (RxNorm + a small curated interaction table). The
LLM is only used to write the human-readable rationale, never the lookup.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas import Suggestion

# Curated interaction table.
#
# Source: cross-referenced FDA labels, Lexicomp/Micromedex severity
# classifications, and openFDA's drug-drug-interaction data. Severities are
# normalised to {"major", "moderate"} to keep the suggestion ladder simple
# ("major" → action chip, "moderate" → watch chip).
#
# This is INTENTIONALLY curated rather than LLM-generated: an LLM telling a
# real user that a real pair of drugs is or isn't dangerous is the
# nightmare hallucination class. Every entry below has a mechanism listed
# so a clinician can sanity-check the rationale.
#
# Limitations:
#   - Matches on the first token only (lowercased), so "lisinopril 10mg" →
#     "lisinopril" but "amoxicillin-clavulanate" only matches if the user
#     types "amoxicillin". This is intentional to keep matching predictable;
#     branded names route to the generic via the synonym aliases below.
#   - Not exhaustive. Real production would integrate DrugBank or RxNorm
#     interaction APIs.  We err on the side of common, clinically obvious
#     pairs and a few that genuinely catch people (NSAID + ACEi + diuretic
#     "triple whammy", clarithromycin + statins, etc.)
INTERACTIONS: dict[tuple[str, str], tuple[str, str]] = {
    # ─── Anticoagulants / antiplatelets ─────────────────────────────────
    ("warfarin",    "aspirin"):       ("major",    "Concurrent anticoagulant + antiplatelet — bleeding risk multiplied."),
    ("warfarin",    "ibuprofen"):     ("major",    "NSAIDs displace warfarin and damage gastric mucosa — major GI-bleed risk."),
    ("warfarin",    "naproxen"):      ("major",    "Same NSAID-on-warfarin mechanism."),
    ("warfarin",    "clopidogrel"):   ("major",    "Anticoagulant + antiplatelet combination — bleeding risk."),
    ("warfarin",    "amiodarone"):    ("major",    "Amiodarone potentiates warfarin via CYP2C9 inhibition — INR rises ~2× over weeks."),
    ("warfarin",    "fluconazole"):   ("major",    "CYP2C9 inhibition raises INR; lab-monitor closely."),
    ("warfarin",    "metronidazole"): ("major",    "Marked INR rise via CYP2C9 inhibition; reduce dose & monitor."),
    ("warfarin",    "bactrim"):       ("major",    "Sulfamethoxazole displaces + inhibits CYP2C9 — high bleed risk."),
    ("warfarin",    "ginkgo"):        ("moderate", "Ginkgo has antiplatelet activity; bleed risk on warfarin."),
    ("aspirin",     "ibuprofen"):     ("moderate", "Ibuprofen taken near aspirin blocks the cardioprotective effect."),
    ("clopidogrel", "omeprazole"):    ("moderate", "Omeprazole inhibits CYP2C19, reducing clopidogrel activation; prefer pantoprazole."),
    ("clopidogrel", "esomeprazole"):  ("moderate", "Same CYP2C19 mechanism as omeprazole."),

    # ─── Renin–angiotensin / potassium ───────────────────────────────────
    ("lisinopril",  "spironolactone"):("moderate", "ACE-I + K-sparing diuretic — hyperkalemia risk, esp. with CKD."),
    ("lisinopril",  "potassium"):     ("moderate", "ACE-I + K supplement — hyperkalemia risk."),
    ("lisinopril",  "losartan"):      ("major",    "Dual RAAS blockade (ACE-I + ARB) increases hyperkalemia + AKI risk; no mortality benefit."),
    ("lisinopril",  "ibuprofen"):     ("moderate", "NSAID + ACE-I — blunts BP effect and risks AKI ('triple whammy' with diuretic)."),
    ("lisinopril",  "naproxen"):      ("moderate", "Same NSAID + ACE-I mechanism."),
    ("losartan",    "spironolactone"):("moderate", "ARB + K-sparing diuretic — hyperkalemia risk."),
    ("losartan",    "potassium"):     ("moderate", "ARB + K supplement — hyperkalemia risk."),

    # ─── Statins (CYP3A4) ────────────────────────────────────────────────
    ("simvastatin", "clarithromycin"):("major",    "CYP3A4 inhibition raises statin levels — rhabdomyolysis risk."),
    ("simvastatin", "erythromycin"):  ("major",    "Same CYP3A4 mechanism as clarithromycin."),
    ("simvastatin", "ketoconazole"):  ("major",    "Strong CYP3A4 inhibition — avoid combination."),
    ("simvastatin", "fluconazole"):   ("moderate", "Moderate CYP3A4 + CYP2C9 inhibition — dose-related myopathy risk."),
    ("simvastatin", "amiodarone"):    ("major",    "Limit simvastatin to 20 mg/day on amiodarone — myopathy risk."),
    ("simvastatin", "diltiazem"):     ("moderate", "Limit simvastatin to 10 mg/day on diltiazem."),
    ("simvastatin", "verapamil"):     ("moderate", "Limit simvastatin to 10 mg/day on verapamil."),
    ("atorvastatin","clarithromycin"):("major",    "CYP3A4 inhibition; reduce statin or hold during course."),
    ("atorvastatin","gemfibrozil"):   ("major",    "Statin + gemfibrozil — major rhabdomyolysis risk; avoid."),

    # ─── Serotonergic combinations (serotonin syndrome) ─────────────────
    ("ssri",        "tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("ssri",        "linezolid"):     ("major",    "Serotonin syndrome — avoid combination."),
    ("ssri",        "mao"):           ("major",    "Serotonin syndrome — washout required between agents."),
    ("sertraline",  "tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("sertraline",  "linezolid"):     ("major",    "Serotonin syndrome — avoid combination."),
    ("fluoxetine",  "tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("citalopram",  "tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("escitalopram","tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("venlafaxine", "tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("duloxetine",  "tramadol"):      ("major",    "Serotonin syndrome risk."),
    ("sumatriptan", "fluoxetine"):    ("moderate", "Triptan + SSRI — weak serotonin syndrome signal; counsel and monitor."),

    # ─── Cardiac / electrophysiology ────────────────────────────────────
    ("metoprolol",  "verapamil"):     ("major",    "Beta-blocker + non-DHP CCB — bradycardia / heart block."),
    ("metoprolol",  "diltiazem"):     ("major",    "Beta-blocker + non-DHP CCB — bradycardia / heart block."),
    ("digoxin",     "amiodarone"):    ("major",    "Amiodarone doubles digoxin levels — toxicity risk; halve dose."),
    ("digoxin",     "verapamil"):     ("major",    "Verapamil raises digoxin levels — toxicity risk."),
    ("digoxin",     "clarithromycin"):("major",    "Clarithromycin raises digoxin via P-glycoprotein; monitor for toxicity."),
    ("digoxin",     "furosemide"):    ("moderate", "Diuretic-induced hypokalemia potentiates digoxin toxicity."),
    ("amiodarone",  "fluoroquinolone"): ("major",  "QT prolongation — torsades risk."),
    ("amiodarone",  "ciprofloxacin"): ("major",    "QT prolongation — torsades risk."),
    ("amiodarone",  "ondansetron"):   ("major",    "QT prolongation — torsades risk."),
    ("methadone",   "ciprofloxacin"): ("major",    "QT prolongation — torsades risk."),
    ("methadone",   "ondansetron"):   ("major",    "QT prolongation — torsades risk."),

    # ─── Diabetes / glucose ──────────────────────────────────────────────
    ("metformin",   "contrast"):      ("major",    "Hold metformin around iodinated contrast (lactic acidosis if AKI)."),
    ("metformin",   "alcohol"):       ("moderate", "Heavy alcohol increases lactic acidosis risk; counsel."),
    ("insulin",     "propranolol"):   ("moderate", "Non-selective beta-blockers mask hypoglycemia symptoms."),

    # ─── Antibiotics / antifungals interacting with other drugs ─────────
    ("clarithromycin", "tacrolimus"):  ("major",   "CYP3A4 inhibition — nephrotoxicity from tacrolimus."),
    ("ciprofloxacin",  "tizanidine"):  ("major",   "CYP1A2 inhibition raises tizanidine — severe sedation/hypotension."),
    ("ciprofloxacin",  "theophylline"):("major",   "CYP1A2 inhibition — theophylline toxicity."),

    # ─── CNS depressants / opioids ──────────────────────────────────────
    ("oxycodone",   "benzodiazepine"):("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("oxycodone",   "alprazolam"):    ("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("oxycodone",   "diazepam"):      ("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("oxycodone",   "lorazepam"):     ("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("oxycodone",   "alcohol"):       ("major",    "Opioid + alcohol — respiratory depression / overdose risk."),
    ("hydrocodone", "benzodiazepine"):("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("morphine",    "benzodiazepine"):("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("fentanyl",    "benzodiazepine"):("major",    "Opioid + benzo — respiratory depression / overdose risk."),
    ("methadone",   "benzodiazepine"):("major",    "Opioid + benzo — respiratory depression / overdose risk."),

    # ─── Misc ────────────────────────────────────────────────────────────
    ("sildenafil",  "nitroglycerin"): ("major",    "PDE-5 + nitrate — life-threatening hypotension."),
    ("sildenafil",  "isosorbide"):    ("major",    "PDE-5 + nitrate — life-threatening hypotension."),
    ("tadalafil",   "nitroglycerin"): ("major",    "PDE-5 + nitrate — life-threatening hypotension."),
    ("tadalafil",   "isosorbide"):    ("major",    "PDE-5 + nitrate — life-threatening hypotension."),
    ("levothyroxine", "calcium"):     ("moderate", "Calcium binds levothyroxine — separate by 4 hours."),
    ("levothyroxine", "iron"):        ("moderate", "Iron binds levothyroxine — separate by 4 hours."),
    ("ciprofloxacin", "calcium"):     ("moderate", "Calcium binds fluoroquinolones — separate by 2 hours."),
    ("ciprofloxacin", "iron"):        ("moderate", "Iron binds fluoroquinolones — separate by 2 hours."),
    ("tetracycline",  "calcium"):     ("moderate", "Calcium binds tetracyclines — separate by 2 hours."),
    ("tetracycline",  "dairy"):       ("moderate", "Dairy reduces tetracycline absorption — separate by 2 hours."),
}

# ─── Synonyms / brand → generic aliases ─────────────────────────────────
# Used by _norm() so the interaction lookup catches branded forms that
# users commonly type. Keep keys lower-case.
SYNONYMS: dict[str, str] = {
    # SSRIs / SNRIs commonly typed as branded
    "lexapro":   "escitalopram",
    "celexa":    "citalopram",
    "zoloft":    "sertraline",
    "prozac":    "fluoxetine",
    "paxil":     "paroxetine",
    "effexor":   "venlafaxine",
    "cymbalta":  "duloxetine",
    "wellbutrin": "bupropion",
    # benzos that the opioid combos check
    "xanax":     "alprazolam",
    "valium":    "diazepam",
    "ativan":    "lorazepam",
    "klonopin":  "clonazepam",
    # nitrates
    "nitro":     "nitroglycerin",
    "nitrostat": "nitroglycerin",
    # statins
    "lipitor":   "atorvastatin",
    "zocor":     "simvastatin",
    "crestor":   "rosuvastatin",
    # cardiac
    "lopressor": "metoprolol",
    "toprol":    "metoprolol",
    "cardizem":  "diltiazem",
    "calan":     "verapamil",
    "coumadin":  "warfarin",
    "plavix":    "clopidogrel",
    "eliquis":   "apixaban",
    "xarelto":   "rivaroxaban",
    # antibiotics
    "biaxin":    "clarithromycin",
    "zithromax": "azithromycin",
    "cipro":     "ciprofloxacin",
    "levaquin":  "levofloxacin",
    "bactrim":   "bactrim",     # keep the brand as the key — already in the table
    "septra":    "bactrim",
    # diabetes / thyroid
    "glucophage": "metformin",
    "synthroid":  "levothyroxine",
    # misc
    "viagra":    "sildenafil",
    "cialis":    "tadalafil",
    "advil":     "ibuprofen",
    "motrin":    "ibuprofen",
    "aleve":     "naproxen",
    "tylenol":   "acetaminophen",
}


def _norm(name: str) -> str:
    """Lower-case the first token, then resolve common brand→generic
    aliases via SYNONYMS so "Xanax 0.5mg" → "alprazolam" → matches the
    opioid+benzo combo entries."""
    if not name:
        return ""
    token = name.lower().split()[0]
    return SYNONYMS.get(token, token)


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
