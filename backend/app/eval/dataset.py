"""
Synthetic gold-labeled eval dataset.

Hand-authored across input modalities and clinical scenarios so we can
measure extraction precision/recall, RAG retrieval quality, PII scrubbing
coverage, and groundedness on a fixed, reproducible benchmark.

Each example carries:
  - id: stable identifier for cross-run comparison
  - modality: text / pdf / image / voice (drives expected pipeline path)
  - input: raw source (string for text; description for image/pdf/voice)
  - gold: the canonical structured extraction expected
  - tags: difficulty + scenario tags for sliced reports
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


Modality = Literal["text", "pdf", "image", "voice"]


@dataclass
class GoldExample:
    id: str
    modality: Modality
    input: str
    gold: dict
    tags: list[str] = field(default_factory=list)


# ---------- extraction gold set ---------------------------------------------

EXTRACTION_GOLD: list[GoldExample] = [
    GoldExample(
        id="ex01_hypertension_followup",
        modality="text",
        input=(
            "Follow-up visit 2026-03-10. Patient reports good adherence to lisinopril 10mg daily. "
            "Home BP cuff readings averaging 132/84. No dizziness or cough. Continuing current "
            "regimen. Will recheck BP and basic metabolic panel in 3 months."
        ),
        gold={
            "diagnoses": [{"condition": "Essential hypertension", "icd10": "I10", "status": "active"}],
            "medications": [{"name": "Lisinopril", "dose": "10mg", "frequency": "QD"}],
            "vitals": [{"type": "bp", "value": "132/84", "unit": "mmHg"}],
            "labs": [],
            "symptoms": [],
            "red_flags": [],
        },
        tags=["text", "easy", "chronic_dx"],
    ),
    GoldExample(
        id="ex02_diabetes_panel",
        modality="text",
        input=(
            "Quarterly diabetes review. A1C 7.5% (up from 6.9%), LDL 142, HDL 41, "
            "triglycerides 168, creatinine 1.0, eGFR 78. BP 138/86, weight 87 kg. "
            "Starting atorvastatin 20mg QHS, increasing metformin to 1000mg BID."
        ),
        gold={
            "diagnoses": [{"condition": "Type 2 diabetes mellitus", "icd10": "E11.9", "status": "active"}],
            "medications": [
                {"name": "Atorvastatin", "dose": "20mg", "frequency": "QHS"},
                {"name": "Metformin", "dose": "1000mg", "frequency": "BID"},
            ],
            "vitals": [
                {"type": "bp", "value": "138/86", "unit": "mmHg"},
                {"type": "weight", "value": "87", "unit": "kg"},
            ],
            "labs": [
                {"test": "HbA1c", "value": "7.5", "unit": "%", "flag": "high"},
                {"test": "LDL", "value": "142", "unit": "mg/dL", "flag": "high"},
                {"test": "HDL", "value": "41", "unit": "mg/dL", "flag": "normal"},
                {"test": "Triglycerides", "value": "168", "unit": "mg/dL", "flag": "high"},
                {"test": "Creatinine", "value": "1.0", "unit": "mg/dL", "flag": "normal"},
            ],
            "symptoms": [],
            "red_flags": [],
        },
        tags=["text", "medium", "multi_field"],
    ),
    GoldExample(
        id="ex03_chest_pain_red_flag",
        modality="text",
        input=(
            "Pt presents to ED with substernal chest pain radiating to left arm, onset 2 hours ago. "
            "Diaphoretic. BP 158/96, HR 102. EKG shows ST elevation V2-V4. Troponin pending."
        ),
        gold={
            "diagnoses": [{"condition": "Acute MI (suspected)", "icd10": "I21", "status": "suspected"}],
            "medications": [],
            "vitals": [
                {"type": "bp", "value": "158/96", "unit": "mmHg"},
                {"type": "hr", "value": "102", "unit": "bpm"},
            ],
            "labs": [],
            "symptoms": [
                {"description": "Substernal chest pain radiating to left arm", "onset": "2 hours", "severity": "severe"},
                {"description": "Diaphoresis", "severity": "moderate"},
            ],
            "red_flags": [
                {"finding": "ST elevation V2-V4 with chest pain", "urgency": "emergent"},
            ],
        },
        tags=["text", "hard", "emergency"],
    ),
    GoldExample(
        id="ex04_pdf_lab_only",
        modality="pdf",
        input=(
            "LABORATORY REPORT\n"
            "Date: 2026-04-22\n"
            "TSH: 4.8 mIU/L (ref 0.4-4.0) HIGH\n"
            "Free T4: 1.1 ng/dL (ref 0.8-1.8)\n"
            "Vitamin D 25-OH: 18 ng/mL (ref 30-100) LOW\n"
            "Ferritin: 22 ng/mL (ref 24-336) LOW"
        ),
        gold={
            "diagnoses": [],
            "medications": [],
            "vitals": [],
            "labs": [
                {"test": "TSH", "value": "4.8", "unit": "mIU/L", "flag": "high"},
                {"test": "Free T4", "value": "1.1", "unit": "ng/dL", "flag": "normal"},
                {"test": "Vitamin D 25-OH", "value": "18", "unit": "ng/mL", "flag": "low"},
                {"test": "Ferritin", "value": "22", "unit": "ng/mL", "flag": "low"},
            ],
            "symptoms": [],
            "red_flags": [],
        },
        tags=["pdf", "medium", "labs_only"],
    ),
    GoldExample(
        id="ex05_voice_symptom",
        modality="voice",
        input=(
            "I've been having pretty bad headaches for the past five days. They start in the "
            "morning and last for hours. Light bothers me. No fever, no neck stiffness. "
            "I'm not on any new meds."
        ),
        gold={
            "diagnoses": [],
            "medications": [],
            "vitals": [],
            "labs": [],
            "symptoms": [
                {"description": "Morning headaches with photophobia", "onset": "5 days", "severity": "moderate"},
            ],
            "red_flags": [],
        },
        tags=["voice", "easy", "symptom_only"],
    ),
    GoldExample(
        id="ex06_image_skin",
        modality="image",
        input="(skin photo: erythematous, well-demarcated annular lesion ~3cm on right forearm with central clearing, mild scaling at the border)",
        gold={
            "diagnoses": [],
            "medications": [],
            "vitals": [],
            "labs": [],
            "symptoms": [
                {"description": "Erythematous annular lesion ~3cm with central clearing and scaling border, right forearm",
                 "severity": "mild"},
            ],
            "red_flags": [],
        },
        tags=["image", "medium", "dermatology"],
    ),
    GoldExample(
        id="ex07_polypharmacy",
        modality="text",
        input=(
            "Medication reconciliation: Warfarin 5mg QD, Aspirin 81mg QD, Ibuprofen 600mg TID prn, "
            "Lisinopril 20mg QD, Metformin 1000mg BID, Atorvastatin 40mg QHS."
        ),
        gold={
            "diagnoses": [],
            "medications": [
                {"name": "Warfarin", "dose": "5mg", "frequency": "QD"},
                {"name": "Aspirin", "dose": "81mg", "frequency": "QD"},
                {"name": "Ibuprofen", "dose": "600mg", "frequency": "TID"},
                {"name": "Lisinopril", "dose": "20mg", "frequency": "QD"},
                {"name": "Metformin", "dose": "1000mg", "frequency": "BID"},
                {"name": "Atorvastatin", "dose": "40mg", "frequency": "QHS"},
            ],
            "vitals": [], "labs": [], "symptoms": [], "red_flags": [],
        },
        tags=["text", "medium", "meds_only", "interaction_test"],
    ),
    GoldExample(
        id="ex08_pdf_discharge",
        modality="pdf",
        input=(
            "DISCHARGE SUMMARY 2026-05-01\n"
            "Admit dx: Community-acquired pneumonia (J18.9)\n"
            "Hospital course: 4-day stay, treated with IV ceftriaxone + azithromycin. "
            "Switched to PO amoxicillin-clavulanate on day 3. Afebrile last 24h.\n"
            "Discharge meds: Amoxicillin-clavulanate 875mg BID x 7 days, continued home lisinopril 10mg QD.\n"
            "Vitals at discharge: BP 124/78, HR 76, SpO2 96% RA, Temp 98.2 F."
        ),
        gold={
            "diagnoses": [{"condition": "Community-acquired pneumonia", "icd10": "J18.9", "status": "active"}],
            "medications": [
                {"name": "Amoxicillin-clavulanate", "dose": "875mg", "frequency": "BID"},
                {"name": "Lisinopril", "dose": "10mg", "frequency": "QD"},
            ],
            "vitals": [
                {"type": "bp", "value": "124/78", "unit": "mmHg"},
                {"type": "hr", "value": "76", "unit": "bpm"},
                {"type": "spo2", "value": "96", "unit": "%"},
                {"type": "temp", "value": "98.2", "unit": "F"},
            ],
            "labs": [], "symptoms": [], "red_flags": [],
        },
        tags=["pdf", "hard", "multi_section"],
    ),
    GoldExample(
        id="ex09_empty_input",
        modality="text",
        input="No complaints, feeling well today.",
        gold={"diagnoses": [], "medications": [], "vitals": [], "labs": [], "symptoms": [], "red_flags": []},
        tags=["text", "easy", "empty_extraction"],
    ),
    GoldExample(
        id="ex10_stroke_red_flag",
        modality="voice",
        input=(
            "My grandmother woke up this morning and her right arm and leg feel weak. "
            "Her speech is slurred. This started about an hour ago."
        ),
        gold={
            "diagnoses": [],
            "medications": [], "vitals": [], "labs": [],
            "symptoms": [
                {"description": "Right-sided weakness", "onset": "1 hour", "severity": "severe"},
                {"description": "Slurred speech", "onset": "1 hour", "severity": "severe"},
            ],
            "red_flags": [
                {"finding": "Acute focal neurological deficit", "urgency": "emergent"},
            ],
        },
        tags=["voice", "hard", "emergency", "stroke"],
    ),
    GoldExample(
        id="ex11_pediatric_vitals",
        modality="text",
        input="Well-child visit, 4-year-old. Weight 17.2 kg, height 102 cm. BP 95/60, HR 96, Temp 98.4 F.",
        gold={
            "diagnoses": [],
            "medications": [], "labs": [], "symptoms": [], "red_flags": [],
            "vitals": [
                {"type": "weight", "value": "17.2", "unit": "kg"},
                {"type": "bp", "value": "95/60", "unit": "mmHg"},
                {"type": "hr", "value": "96", "unit": "bpm"},
                {"type": "temp", "value": "98.4", "unit": "F"},
            ],
        },
        tags=["text", "easy", "pediatric"],
    ),
    GoldExample(
        id="ex12_complex_oncology",
        modality="pdf",
        input=(
            "Oncology follow-up 2026-02-14. Pt s/p left mastectomy + ALND for stage IIB IDC, "
            "ER+/PR+/HER2-. Currently on tamoxifen 20mg QD x 6 months. Reports mild hot flashes. "
            "CA 27-29: 18 U/mL (normal). LFTs WNL. PE: no axillary or supraclavicular adenopathy. "
            "Plan: continue tamoxifen, repeat tumor markers in 3 months."
        ),
        gold={
            "diagnoses": [
                {"condition": "Stage IIB invasive ductal carcinoma", "icd10": "C50.9", "status": "active"},
            ],
            "medications": [{"name": "Tamoxifen", "dose": "20mg", "frequency": "QD"}],
            "vitals": [],
            "labs": [
                {"test": "CA 27-29", "value": "18", "unit": "U/mL", "flag": "normal"},
            ],
            "symptoms": [{"description": "Hot flashes", "severity": "mild"}],
            "red_flags": [],
        },
        tags=["pdf", "hard", "oncology"],
    ),
]


# ---------- RAG retrieval queries -------------------------------------------

@dataclass
class RagQuery:
    query: str
    relevant_ids: set[str]   # gold-standard relevant example ids
    tags: list[str] = field(default_factory=list)


RAG_QUERIES: list[RagQuery] = [
    RagQuery("When was my last A1C and what was it?", {"ex02_diabetes_panel"}, ["lookup", "single"]),
    RagQuery("Is my blood pressure trending up?",
             {"ex01_hypertension_followup", "ex02_diabetes_panel", "ex11_pediatric_vitals"},
             ["trend", "multi"]),
    RagQuery("What medications am I on for diabetes?", {"ex02_diabetes_panel", "ex07_polypharmacy"}, ["meds"]),
    RagQuery("Have I had a stroke or stroke symptoms?", {"ex10_stroke_red_flag"}, ["red_flag"]),
    RagQuery("Tell me about my thyroid labs.", {"ex04_pdf_lab_only"}, ["labs"]),
    RagQuery("What's the skin lesion on my arm?", {"ex06_image_skin"}, ["image"]),
    RagQuery("Was I hospitalised recently?", {"ex08_pdf_discharge"}, ["history"]),
    RagQuery("Am I on warfarin?", {"ex07_polypharmacy"}, ["meds", "lookup"]),
    RagQuery("Should I worry about chest pain?", {"ex03_chest_pain_red_flag"}, ["red_flag"]),
    RagQuery("What's my cancer treatment plan?", {"ex12_complex_oncology"}, ["oncology"]),
]


# ---------- PII test set ----------------------------------------------------

@dataclass
class PIICase:
    raw: str
    must_scrub: list[str]   # substrings that must be redacted out
    must_keep: list[str]    # substrings that must remain (clinical info)


PII_CASES: list[PIICase] = [
    PIICase(
        raw="Patient John Smith, DOB 04/12/1981, SSN 123-45-6789, presents with HTN. MRN: 84772911.",
        must_scrub=["123-45-6789", "84772911", "04/12/1981"],
        must_keep=["HTN"],
    ),
    PIICase(
        raw="Contact: jane.doe@example.com or (415) 555-2381. Pt reports A1C 7.2%.",
        must_scrub=["jane.doe@example.com", "(415) 555-2381"],
        must_keep=["A1C 7.2%"],
    ),
    PIICase(
        raw="DOB: 12-15-1995. BP 132/84. Lisinopril 10mg.",
        must_scrub=["12-15-1995"],
        must_keep=["132/84", "Lisinopril"],
    ),
    PIICase(
        raw="MRN 12345 admitted with pneumonia. SSN 987-65-4321 on file.",
        must_scrub=["12345", "987-65-4321"],
        must_keep=["pneumonia"],
    ),
    PIICase(
        raw="Email rishika@folio.app, phone 415.555.7700, no acute issues.",
        must_scrub=["rishika@folio.app", "415.555.7700"],
        must_keep=["no acute issues"],
    ),
    PIICase(
        raw="Pure clinical note: A1C 6.4%, BP 124/76, on metformin 1000mg BID.",
        must_scrub=[],   # nothing should be scrubbed
        must_keep=["A1C 6.4%", "124/76", "metformin 1000mg BID"],
    ),
]


# ---------- Chat groundedness probes ----------------------------------------

@dataclass
class ChatProbe:
    """A canned chat question with a known correct factual answer and the
    report ids that should be cited as evidence."""
    question: str
    must_contain_any: list[str]   # at least one of these substrings should appear in the reply
    must_cite: set[str]           # report ids that should be in the citation set
    must_avoid: list[str] = field(default_factory=list)  # things that would indicate hallucination


CHAT_PROBES: list[ChatProbe] = [
    ChatProbe(
        question="When was my last A1C?",
        must_contain_any=["7.5", "diabetes"],
        must_cite={"ex02_diabetes_panel"},
    ),
    ChatProbe(
        question="I'm having sudden right-sided weakness and slurred speech",
        must_contain_any=["911", "ER", "emergency", "urgent"],
        must_cite=set(),
        must_avoid=["take ibuprofen", "wait", "monitor at home"],
    ),
    ChatProbe(
        question="What's my LDL right now?",
        must_contain_any=["142"],
        must_cite={"ex02_diabetes_panel"},
        must_avoid=["I don't have", "no record"],   # we DO have it
    ),
]


def all_modality_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for ex in EXTRACTION_GOLD:
        out[ex.modality] = out.get(ex.modality, 0) + 1
    return out
