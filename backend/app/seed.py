"""
Seed Folio with a believable longitudinal record. ~14 reports over 10 months
covering: gradual onset of hypertension, pre-diabetes that progresses to T2DM,
hyperlipidemia, and treatment response. Mix of input types so every page has
real content on first launch.

Run with:
    docker compose exec backend python -m app.seed
"""
import asyncio
from datetime import datetime, timedelta

from .auth import create_user, find_user_by_username
from .db import ensure_indexes, get_db
from .pipeline.persist import persist_report
from .rag.store import reindex_user
from .schemas import (
    Diagnosis, ExtractedReport, Lab, Medication, RedFlag, Symptom, Vital,
)
from .suggestions.runner import run_all


def _iso(days_ago: int, hour: int = 10) -> str:
    base = datetime.utcnow() - timedelta(days=days_ago)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


# --- Patient narrative -------------------------------------------------------
# 32 y/o, family history of T2DM. Started routine annual physical 10 months
# ago. Borderline labs evolved into pre-diabetes and Stage 1 HTN. Lisinopril
# started, metformin added, statin added. Most recent visit shows therapy
# starting to work.
# -----------------------------------------------------------------------------

SEED: list[ExtractedReport] = [
    # 1. ~10 months ago — annual physical, baseline
    ExtractedReport(
        input_type="pdf",
        uploaded_at=_iso(305),
        diagnoses=[],
        medications=[],
        vitals=[
            Vital(type="bp",     value="124/78", unit="mmHg",   recorded_at=_iso(305)),
            Vital(type="hr",     value="72",     unit="bpm",    recorded_at=_iso(305)),
            Vital(type="weight", value="86",     unit="kg",     recorded_at=_iso(305)),
            Vital(type="bmi",    value="27.5",   unit="kg/m2",  recorded_at=_iso(305)),
        ],
        labs=[
            Lab(test="HbA1c",       value="5.5",  unit="%",      reference_range="<5.7",     flag="normal"),
            Lab(test="LDL",         value="118",  unit="mg/dL",  reference_range="<100",     flag="high"),
            Lab(test="HDL",         value="48",   unit="mg/dL",  reference_range=">40",      flag="normal"),
            Lab(test="Triglycerides", value="148", unit="mg/dL", reference_range="<150",     flag="normal"),
            Lab(test="Creatinine",  value="0.9",  unit="mg/dL",  reference_range="0.6-1.2",  flag="normal"),
            Lab(test="TSH",         value="2.1",  unit="mIU/L",  reference_range="0.4-4.0",  flag="normal"),
        ],
        symptoms=[],
        red_flags=[],
        raw_summary="Annual physical. Generally healthy with mildly elevated LDL and overweight BMI; family history of T2DM noted.",
        source_text="Annual exam summary. Vitals: BP 124/78, HR 72, Wt 86 kg, BMI 27.5. Labs: A1C 5.5%, LDL 118, HDL 48, Trig 148, Cr 0.9, TSH 2.1. Recommendation: lifestyle counselling. FH: father T2DM dx age 50.",
    ),

    # 2. 9 months — text journal entry
    ExtractedReport(
        input_type="text",
        uploaded_at=_iso(270),
        diagnoses=[],
        medications=[],
        vitals=[],
        labs=[],
        symptoms=[Symptom(description="Occasional fatigue in afternoons", onset="3 weeks", severity="mild")],
        red_flags=[],
        raw_summary="Journal note: afternoon fatigue, otherwise well.",
        source_text="Feeling more tired than usual the last 3 weeks, especially around 3-4pm. Sleep is fine, ~7 hrs. No other complaints.",
    ),

    # 3. 8 months — voice note about workout
    ExtractedReport(
        input_type="voice",
        uploaded_at=_iso(240),
        diagnoses=[],
        medications=[],
        vitals=[Vital(type="hr", value="142", unit="bpm", recorded_at=_iso(240))],
        labs=[],
        symptoms=[],
        red_flags=[],
        raw_summary="Voice memo: peak HR 142 during workout, no symptoms.",
        source_text="Voice transcript. Hit 142 on the bike today, felt fine. Recovered quickly. Want to start tracking workouts here.",
    ),

    # 4. 7 months — PDF lab work, BP creeping up
    ExtractedReport(
        input_type="pdf",
        uploaded_at=_iso(210),
        diagnoses=[],
        medications=[],
        vitals=[
            Vital(type="bp",     value="130/84", unit="mmHg",  recorded_at=_iso(210)),
            Vital(type="weight", value="87",     unit="kg",    recorded_at=_iso(210)),
            Vital(type="bmi",    value="27.8",   unit="kg/m2", recorded_at=_iso(210)),
        ],
        labs=[
            Lab(test="HbA1c", value="5.8", unit="%",     reference_range="<5.7", flag="high"),
            Lab(test="LDL",   value="124", unit="mg/dL", reference_range="<100", flag="high"),
        ],
        symptoms=[],
        red_flags=[],
        raw_summary="Routine bloodwork: A1C now 5.8% (pre-diabetic range), LDL 124. BP 130/84.",
        source_text="3-month follow-up labs. A1C 5.8% (was 5.5%), LDL 124 (was 118), BP 130/84 (was 124/78).",
    ),

    # 5. 6 months — image of paper visit summary
    ExtractedReport(
        input_type="image",
        uploaded_at=_iso(180),
        diagnoses=[
            Diagnosis(condition="Pre-diabetes", icd10="R73.03", status="active", confidence=0.85),
            Diagnosis(condition="Essential hypertension", icd10="I10", status="suspected", confidence=0.6),
        ],
        medications=[],
        vitals=[
            Vital(type="bp", value="134/86", unit="mmHg", recorded_at=_iso(180)),
        ],
        labs=[],
        symptoms=[Symptom(description="Increased thirst", onset="1 month", severity="mild")],
        red_flags=[],
        raw_summary="Doctor visit photo: pre-diabetes confirmed, BP elevated, lifestyle plan started.",
        source_text="Photo of clinic visit summary. Pre-diabetes confirmed. BP 134/86 — borderline. Plan: DASH diet, 150 min/wk exercise. Recheck 3mo.",
    ),

    # 6. 5 months — text entry, started lisinopril
    ExtractedReport(
        input_type="text",
        uploaded_at=_iso(150),
        diagnoses=[
            Diagnosis(condition="Essential hypertension", icd10="I10", status="active", confidence=0.85),
        ],
        medications=[
            Medication(name="Lisinopril", dose="10mg", frequency="QD", purpose="Hypertension"),
        ],
        vitals=[
            Vital(type="bp", value="138/88", unit="mmHg", recorded_at=_iso(150)),
        ],
        labs=[],
        symptoms=[],
        red_flags=[],
        raw_summary="Doctor started lisinopril 10mg daily; BP 138/88 today.",
        source_text="Started Lisinopril 10mg QD this morning. BP at home: 138/88. Doc said monitor for dry cough.",
    ),

    # 7. 4 months — voice note, side effect
    ExtractedReport(
        input_type="voice",
        uploaded_at=_iso(120),
        diagnoses=[],
        medications=[],
        vitals=[Vital(type="bp", value="132/84", unit="mmHg", recorded_at=_iso(120))],
        labs=[],
        symptoms=[Symptom(description="Mild dry cough since starting lisinopril", onset="3 weeks", severity="mild")],
        red_flags=[],
        raw_summary="Voice memo: dry cough since lisinopril, BP improving.",
        source_text="Voice. Dry cough still there. Annoying but not bad. BP 132/84, definitely better. Will check in with doc next visit.",
    ),

    # 8. 3 months — PDF lab panel showing diabetes onset
    ExtractedReport(
        input_type="pdf",
        uploaded_at=_iso(90),
        diagnoses=[
            Diagnosis(condition="Type 2 diabetes mellitus", icd10="E11.9", status="active", confidence=0.85),
            Diagnosis(condition="Essential hypertension", icd10="I10", status="active", confidence=0.9),
        ],
        medications=[
            Medication(name="Lisinopril", dose="10mg",  frequency="QD",  purpose="Hypertension"),
            Medication(name="Metformin",  dose="500mg", frequency="BID", purpose="Glycemic control"),
        ],
        vitals=[
            Vital(type="bp",      value="132/82", unit="mmHg",   recorded_at=_iso(90)),
            Vital(type="weight",  value="88",     unit="kg",     recorded_at=_iso(90)),
            Vital(type="glucose", value="156",    unit="mg/dL",  recorded_at=_iso(90)),
        ],
        labs=[
            Lab(test="HbA1c",      value="6.6",  unit="%",      reference_range="<5.7",    flag="high"),
            Lab(test="LDL",        value="132",  unit="mg/dL",  reference_range="<100",    flag="high"),
            Lab(test="HDL",        value="46",   unit="mg/dL",  reference_range=">40",     flag="normal"),
            Lab(test="Creatinine", value="0.95", unit="mg/dL",  reference_range="0.6-1.2", flag="normal"),
            Lab(test="ALT",        value="34",   unit="U/L",    reference_range="<40",     flag="normal"),
        ],
        symptoms=[
            Symptom(description="Polyuria, mild blurred vision", onset="6 weeks", severity="mild"),
        ],
        red_flags=[],
        raw_summary="A1C 6.6% — diabetes diagnosed. Started Metformin 500mg BID. LDL still high.",
        source_text="Quarterly visit. A1C 6.6% (was 5.8%), confirms T2DM. LDL 132. BP 132/82 on lisinopril. Started Metformin 500 mg BID.",
    ),

    # 9. 10 weeks — text, GI side effect
    ExtractedReport(
        input_type="text",
        uploaded_at=_iso(70),
        diagnoses=[],
        medications=[],
        vitals=[],
        labs=[],
        symptoms=[Symptom(description="GI upset / loose stools first 2 weeks of metformin, mostly resolved", onset="2 weeks", severity="moderate")],
        red_flags=[],
        raw_summary="Note: metformin GI side effects, mostly resolved.",
        source_text="GI was rough first week or two on metformin. Bloating, loose stools. Mostly settled now that I take it with food.",
    ),

    # 10. 8 weeks — image of pharmacy printout
    ExtractedReport(
        input_type="image",
        uploaded_at=_iso(56),
        diagnoses=[],
        medications=[
            Medication(name="Lisinopril", dose="10mg",   frequency="QD",  purpose="Hypertension"),
            Medication(name="Metformin",  dose="1000mg", frequency="BID", purpose="Glycemic control"),
        ],
        vitals=[],
        labs=[],
        symptoms=[],
        red_flags=[],
        raw_summary="Photo of pharmacy printout: Metformin titrated up to 1000 mg BID.",
        source_text="Pharmacy bag photo. Metformin increased to 1000mg twice daily. Lisinopril unchanged at 10mg.",
    ),

    # 11. 5 weeks — voice, headaches return
    ExtractedReport(
        input_type="voice",
        uploaded_at=_iso(35),
        diagnoses=[],
        medications=[],
        vitals=[Vital(type="bp", value="146/94", unit="mmHg", recorded_at=_iso(35))],
        labs=[],
        symptoms=[Symptom(description="Persistent morning headaches", onset="10 days", severity="moderate")],
        red_flags=[RedFlag(finding="Headache + elevated BP", reason="Rule out hypertensive urgency if symptoms worsen", urgency="soon")],
        raw_summary="Voice memo: morning headaches plus BP 146/94 — flagged for clinician follow-up.",
        source_text="Voice transcript. Headaches every morning past 10 days. Cuff says 146/94 twice in a row. Going to call the office.",
    ),

    # 12. 3 weeks — PDF, lipid + statin start
    ExtractedReport(
        input_type="pdf",
        uploaded_at=_iso(21),
        diagnoses=[
            Diagnosis(condition="Hyperlipidemia", icd10="E78.5", status="active", confidence=0.85),
            Diagnosis(condition="Essential hypertension", icd10="I10", status="active", confidence=0.95),
            Diagnosis(condition="Type 2 diabetes mellitus", icd10="E11.9", status="active", confidence=0.92),
        ],
        medications=[
            Medication(name="Lisinopril",   dose="20mg",   frequency="QD",  purpose="Hypertension"),
            Medication(name="Metformin",    dose="1000mg", frequency="BID", purpose="Glycemic control"),
            Medication(name="Atorvastatin", dose="20mg",   frequency="QHS", purpose="Hyperlipidemia"),
            Medication(name="Aspirin",      dose="81mg",   frequency="QD",  purpose="Cardioprotection"),
        ],
        vitals=[
            Vital(type="bp",     value="138/88", unit="mmHg", recorded_at=_iso(21)),
            Vital(type="weight", value="87",     unit="kg",   recorded_at=_iso(21)),
            Vital(type="bmi",    value="27.8",   unit="kg/m2",recorded_at=_iso(21)),
        ],
        labs=[
            Lab(test="HbA1c", value="6.9", unit="%",     reference_range="<5.7", flag="high"),
            Lab(test="LDL",   value="138", unit="mg/dL", reference_range="<100", flag="high"),
            Lab(test="HDL",   value="44",  unit="mg/dL", reference_range=">40",  flag="normal"),
        ],
        symptoms=[],
        red_flags=[],
        raw_summary="Lipid panel: LDL still high. Lisinopril uptitrated, Atorvastatin and aspirin started.",
        source_text="Visit summary PDF. LDL 138 — adding atorvastatin 20mg at bedtime. Lisinopril increased to 20mg. Aspirin 81mg started for cardioprotection. Continue metformin.",
    ),

    # 13. 1 week — text home BP log
    ExtractedReport(
        input_type="text",
        uploaded_at=_iso(7),
        diagnoses=[],
        medications=[],
        vitals=[
            Vital(type="bp", value="128/80", unit="mmHg", recorded_at=_iso(7)),
        ],
        labs=[],
        symptoms=[],
        red_flags=[],
        raw_summary="Home BP log: 128/80, in target range.",
        source_text="Home BP this week, average 128/80 across 6 readings. Headaches haven't come back.",
    ),

    # 14. 2 days ago — comprehensive PDF
    ExtractedReport(
        input_type="pdf",
        uploaded_at=_iso(2),
        diagnoses=[
            Diagnosis(condition="Hyperlipidemia", icd10="E78.5", status="active", confidence=0.9),
            Diagnosis(condition="Essential hypertension", icd10="I10", status="active", confidence=0.95),
            Diagnosis(condition="Type 2 diabetes mellitus", icd10="E11.9", status="active", confidence=0.95),
        ],
        medications=[
            Medication(name="Lisinopril",   dose="20mg",   frequency="QD",  purpose="Hypertension"),
            Medication(name="Metformin",    dose="1000mg", frequency="BID", purpose="Glycemic control"),
            Medication(name="Atorvastatin", dose="20mg",   frequency="QHS", purpose="Hyperlipidemia"),
            Medication(name="Aspirin",      dose="81mg",   frequency="QD",  purpose="Cardioprotection"),
        ],
        vitals=[
            Vital(type="bp",     value="126/80", unit="mmHg", recorded_at=_iso(2)),
            Vital(type="hr",     value="68",     unit="bpm",  recorded_at=_iso(2)),
            Vital(type="weight", value="86",     unit="kg",   recorded_at=_iso(2)),
            Vital(type="bmi",    value="27.5",   unit="kg/m2",recorded_at=_iso(2)),
            Vital(type="spo2",   value="98",     unit="%",    recorded_at=_iso(2)),
        ],
        labs=[
            Lab(test="HbA1c",      value="6.4",  unit="%",      reference_range="<5.7",    flag="high"),
            Lab(test="LDL",        value="98",   unit="mg/dL",  reference_range="<100",    flag="normal"),
            Lab(test="HDL",        value="48",   unit="mg/dL",  reference_range=">40",     flag="normal"),
            Lab(test="Triglycerides", value="124", unit="mg/dL", reference_range="<150",   flag="normal"),
            Lab(test="Creatinine", value="0.9",  unit="mg/dL",  reference_range="0.6-1.2", flag="normal"),
            Lab(test="ALT",        value="30",   unit="U/L",    reference_range="<40",     flag="normal"),
        ],
        symptoms=[],
        red_flags=[],
        raw_summary="Therapy responding: A1C 6.4%, LDL at goal, BP 126/80. Continue current regimen.",
        source_text="Quarterly review. A1C 6.4% (down from 6.9%). LDL 98 (at goal). BP 126/80. Weight stable. Continue current regimen, recheck in 3 months.",
    ),
]


DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo1234"


async def main():
    await ensure_indexes()
    db = get_db()

    # Find or create the demo user; everything is scoped to them.
    existing = await find_user_by_username(DEMO_USERNAME)
    if existing:
        user_id = existing.user_id
    else:
        user = await create_user(DEMO_USERNAME, DEMO_PASSWORD, display_name="Demo Patient")
        user_id = user.user_id
        print(f"created demo user: username='{DEMO_USERNAME}' password='{DEMO_PASSWORD}'")

    # Reset this user's collections so seed is reproducible.
    for coll in ("reports", "diagnoses_master", "medications_master",
                  "vitals_timeline", "labs_timeline",
                  "suggestions", "dismissed_suggestions",
                  "report_embeddings", "consensus_meta"):
        await db[coll].delete_many({"user_id": user_id})

    # Insert in chronological order so master collections reflect the latest state.
    for r in sorted(SEED, key=lambda x: x.uploaded_at):
        await persist_report(r, user_id=user_id)
        print(f"  · {r.uploaded_at[:10]}  {r.input_type:5s}  {r.raw_summary[:64]}")

    # Mark resolved earlier-stage diagnoses (pre-diabetes superseded by T2DM).
    await db.diagnoses_master.update_one(
        {"user_id": user_id, "condition": "pre-diabetes"},
        {"$set": {"status": "resolved"}},
    )

    # Run the suggestion engine on the most recent report so the dashboard
    # has trends, interactions, follow-ups, lifestyle, and risk content.
    latest = max(SEED, key=lambda x: x.uploaded_at)
    print(f"\nGenerating suggestions for latest report ({latest.uploaded_at[:10]})…")
    n = await run_all(latest.report_id, user_id=user_id)
    print(f"  → {len(n)} suggestions inserted")

    # Build the RAG index so chat retrieval has content from day one.
    print("\nBuilding RAG index…")
    try:
        idx_n = await reindex_user(user_id)
        print(f"  → {idx_n} report embeddings stored")
    except Exception as exc:
        print(f"  → embedding skipped ({exc}); chat will fall back to snapshot only")

    print(f"\nSeed complete. Sign in at /login with username '{DEMO_USERNAME}' password '{DEMO_PASSWORD}'.")


if __name__ == "__main__":
    asyncio.run(main())
