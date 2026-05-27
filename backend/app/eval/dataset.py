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

    # ─── 13–30: expansion set ────────────────────────────────────────────
    GoldExample(
        id="ex13_thyroid_followup",
        modality="text",
        input=(
            "Endo follow-up. Pt on levothyroxine 75mcg QD for primary hypothyroidism. "
            "Reports good energy, no cold intolerance. TSH 1.8 mIU/L, Free T4 1.2 ng/dL. "
            "Continue current dose."
        ),
        gold={
            "diagnoses": [{"condition": "Primary hypothyroidism", "icd10": "E03.9", "status": "active"}],
            "medications": [{"name": "Levothyroxine", "dose": "75mcg", "frequency": "QD"}],
            "vitals": [], "symptoms": [], "red_flags": [],
            "labs": [
                {"test": "TSH", "value": "1.8", "unit": "mIU/L", "flag": "normal"},
                {"test": "Free T4", "value": "1.2", "unit": "ng/dL", "flag": "normal"},
            ],
        },
        tags=["text", "easy", "endocrine"],
    ),
    GoldExample(
        id="ex14_med_change",
        modality="text",
        input=(
            "BP not at goal on lisinopril 20mg alone. Discontinuing lisinopril; starting "
            "amlodipine 5mg QD plus HCTZ 12.5mg QD. BP today 152/94, HR 78."
        ),
        gold={
            "diagnoses": [{"condition": "Uncontrolled hypertension", "icd10": "I10", "status": "active"}],
            "medications": [
                {"name": "Amlodipine", "dose": "5mg", "frequency": "QD"},
                {"name": "HCTZ", "dose": "12.5mg", "frequency": "QD"},
                {"name": "Lisinopril", "dose": "20mg", "frequency": "QD", "purpose": "discontinued"},
            ],
            "vitals": [
                {"type": "bp", "value": "152/94", "unit": "mmHg"},
                {"type": "hr", "value": "78", "unit": "bpm"},
            ],
            "labs": [], "symptoms": [], "red_flags": [],
        },
        tags=["text", "medium", "med_change"],
    ),
    GoldExample(
        id="ex15_ct_chest",
        modality="pdf",
        input=(
            "CT CHEST W/O CONTRAST  2026-04-08\n"
            "INDICATION: Chronic cough.\n"
            "FINDINGS: No focal consolidation. No pleural effusion. Two sub-cm "
            "bilateral pulmonary nodules, stable from prior study 2025-10. Mild "
            "centrilobular emphysema in upper lobes.\n"
            "IMPRESSION: 1) Stable pulmonary nodules — Fleischner f/u in 12 mo. "
            "2) Mild emphysema."
        ),
        gold={
            "diagnoses": [
                {"condition": "Pulmonary nodules", "icd10": "R91.1", "status": "active"},
                {"condition": "Emphysema", "icd10": "J43.9", "status": "active"},
            ],
            "medications": [], "vitals": [], "labs": [],
            "symptoms": [{"description": "Chronic cough", "severity": "mild"}],
            "red_flags": [],
        },
        tags=["pdf", "medium", "imaging"],
    ),
    GoldExample(
        id="ex16_asthma_flare",
        modality="text",
        input=(
            "Asthma flare 3 days. Increased SABA use to QID. Peak flow 280 (baseline 410). "
            "Started prednisone 40mg QD x 5 days. No fever. SpO2 95% RA, HR 102."
        ),
        gold={
            "diagnoses": [{"condition": "Asthma exacerbation", "icd10": "J45.901", "status": "active"}],
            "medications": [{"name": "Prednisone", "dose": "40mg", "frequency": "QD"}],
            "vitals": [
                {"type": "spo2", "value": "95", "unit": "%"},
                {"type": "hr", "value": "102", "unit": "bpm"},
            ],
            "labs": [],
            "symptoms": [{"description": "Increased SABA use, reduced peak flow", "onset": "3 days", "severity": "moderate"}],
            "red_flags": [],
        },
        tags=["text", "medium", "pulm"],
    ),
    GoldExample(
        id="ex17_echo_report",
        modality="pdf",
        input=(
            "TRANSTHORACIC ECHO 2026-03-22\n"
            "LV ejection fraction: 35% (moderately reduced)\n"
            "LV size: mildly dilated. Mild concentric hypertrophy.\n"
            "Mitral valve: moderate regurgitation. Aortic valve: trileaflet, no AS.\n"
            "RV size and function normal. No pericardial effusion."
        ),
        gold={
            "diagnoses": [
                {"condition": "Heart failure with reduced ejection fraction", "icd10": "I50.20", "status": "active"},
                {"condition": "Mitral regurgitation", "icd10": "I34.0", "status": "active"},
            ],
            "medications": [], "vitals": [],
            "labs": [{"test": "LV ejection fraction", "value": "35", "unit": "%", "flag": "low"}],
            "symptoms": [],
            "red_flags": [],
        },
        tags=["pdf", "hard", "cardiology"],
    ),
    GoldExample(
        id="ex18_back_pain_voice",
        modality="voice",
        input=(
            "Voice memo. I tweaked my lower back lifting boxes two days ago. It's stiff, hurts "
            "when I bend forward, no shooting pain down the legs, no numbness or tingling. "
            "Tylenol helps a little."
        ),
        gold={
            "diagnoses": [],
            "medications": [{"name": "Tylenol", "dose": "", "frequency": "prn"}],
            "vitals": [], "labs": [],
            "symptoms": [
                {"description": "Lower back stiffness and pain on flexion", "onset": "2 days", "severity": "mild"},
            ],
            "red_flags": [],
        },
        tags=["voice", "easy", "musculoskeletal"],
    ),
    GoldExample(
        id="ex19_migraine_history",
        modality="text",
        input=(
            "Migraine history: 3-4 attacks/month, photophobia + phonophobia + unilateral "
            "throbbing, typically 6-12 hours, often preceded by visual aura. On sumatriptan "
            "100mg prn (effective). Discussing topiramate 50mg BID for prophylaxis."
        ),
        gold={
            "diagnoses": [{"condition": "Migraine with aura", "icd10": "G43.1", "status": "active"}],
            "medications": [
                {"name": "Sumatriptan", "dose": "100mg", "frequency": "prn"},
                {"name": "Topiramate", "dose": "50mg", "frequency": "BID"},
            ],
            "vitals": [], "labs": [],
            "symptoms": [
                {"description": "Recurrent unilateral throbbing headache with photophobia and aura", "severity": "moderate"},
            ],
            "red_flags": [],
        },
        tags=["text", "medium", "neuro"],
    ),
    GoldExample(
        id="ex20_psychiatry_visit",
        modality="pdf",
        input=(
            "Psychiatry follow-up 2026-02-01\n"
            "Dx: Major depressive disorder, recurrent, moderate (F33.1). GAD (F41.1).\n"
            "Medications: Sertraline 100mg QD (8 weeks), buspirone 10mg TID.\n"
            "Sleep improved. PHQ-9: 9 (was 17). GAD-7: 8 (was 14). No SI.\n"
            "Plan: continue sertraline, taper buspirone if anxiety stays controlled."
        ),
        gold={
            "diagnoses": [
                {"condition": "Major depressive disorder, recurrent", "icd10": "F33.1", "status": "active"},
                {"condition": "Generalized anxiety disorder", "icd10": "F41.1", "status": "active"},
            ],
            "medications": [
                {"name": "Sertraline", "dose": "100mg", "frequency": "QD"},
                {"name": "Buspirone", "dose": "10mg", "frequency": "TID"},
            ],
            "vitals": [],
            "labs": [
                {"test": "PHQ-9", "value": "9", "flag": "normal"},
                {"test": "GAD-7", "value": "8", "flag": "normal"},
            ],
            "symptoms": [], "red_flags": [],
        },
        tags=["pdf", "medium", "psychiatry"],
    ),
    GoldExample(
        id="ex21_lipid_followup",
        modality="text",
        input=(
            "Lipid recheck on atorvastatin 40mg QHS x 12 weeks. LDL 88 (was 142), HDL 52, "
            "Trig 110, total chol 168. No muscle pain. Continue atorvastatin. Recheck in 6 mo."
        ),
        gold={
            "diagnoses": [{"condition": "Hyperlipidemia", "icd10": "E78.5", "status": "active"}],
            "medications": [{"name": "Atorvastatin", "dose": "40mg", "frequency": "QHS"}],
            "vitals": [],
            "labs": [
                {"test": "LDL", "value": "88", "unit": "mg/dL", "flag": "normal"},
                {"test": "HDL", "value": "52", "unit": "mg/dL", "flag": "normal"},
                {"test": "Triglycerides", "value": "110", "unit": "mg/dL", "flag": "normal"},
                {"test": "Total cholesterol", "value": "168", "unit": "mg/dL", "flag": "normal"},
            ],
            "symptoms": [], "red_flags": [],
        },
        tags=["text", "easy", "cardio_prev"],
    ),
    GoldExample(
        id="ex22_anaphylaxis_voice",
        modality="voice",
        input=(
            "Voice memo. Ten minutes after eating shrimp at lunch I started getting hives all over "
            "my arms and chest, my throat feels tight, hard to swallow. Used my EpiPen 5 minutes ago. "
            "Heading to the ER."
        ),
        gold={
            "diagnoses": [],
            "medications": [{"name": "Epinephrine", "dose": "EpiPen", "frequency": "prn"}],
            "vitals": [], "labs": [],
            "symptoms": [
                {"description": "Hives on arms and chest after shellfish ingestion", "onset": "10 min", "severity": "severe"},
                {"description": "Throat tightness and difficulty swallowing", "onset": "10 min", "severity": "severe"},
            ],
            "red_flags": [
                {"finding": "Anaphylaxis with airway involvement", "urgency": "emergent"},
            ],
        },
        tags=["voice", "hard", "emergency", "allergy"],
    ),
    GoldExample(
        id="ex23_ra_visit",
        modality="pdf",
        input=(
            "Rheumatology visit. Pt with seropositive rheumatoid arthritis on methotrexate "
            "15mg weekly and hydroxychloroquine 200mg BID. DAS28 score 2.4 (low activity). "
            "Reports occasional morning stiffness <30 min. CRP 4 mg/L, ESR 12 mm/h."
        ),
        gold={
            "diagnoses": [{"condition": "Seropositive rheumatoid arthritis", "icd10": "M05.9", "status": "active"}],
            "medications": [
                {"name": "Methotrexate", "dose": "15mg", "frequency": "weekly"},
                {"name": "Hydroxychloroquine", "dose": "200mg", "frequency": "BID"},
            ],
            "vitals": [],
            "labs": [
                {"test": "CRP", "value": "4", "unit": "mg/L", "flag": "normal"},
                {"test": "ESR", "value": "12", "unit": "mm/h", "flag": "normal"},
                {"test": "DAS28", "value": "2.4", "flag": "normal"},
            ],
            "symptoms": [{"description": "Morning stiffness under 30 minutes", "severity": "mild"}],
            "red_flags": [],
        },
        tags=["pdf", "medium", "rheum"],
    ),
    GoldExample(
        id="ex24_uti",
        modality="text",
        input=(
            "2 days of urinary frequency, dysuria, suprapubic discomfort. No fever, no flank pain. "
            "UA: 3+ leuk esterase, +nitrites, many WBCs, no blood. Starting nitrofurantoin 100mg BID x 5 days."
        ),
        gold={
            "diagnoses": [{"condition": "Acute uncomplicated cystitis", "icd10": "N30.0", "status": "active"}],
            "medications": [{"name": "Nitrofurantoin", "dose": "100mg", "frequency": "BID"}],
            "vitals": [],
            "labs": [
                {"test": "Leukocyte esterase", "value": "3+", "flag": "high"},
                {"test": "Nitrites", "value": "positive", "flag": "high"},
                {"test": "WBC", "value": "many", "flag": "high"},
            ],
            "symptoms": [
                {"description": "Urinary frequency and dysuria with suprapubic discomfort", "onset": "2 days", "severity": "moderate"},
            ],
            "red_flags": [],
        },
        tags=["text", "medium", "infection"],
    ),
    GoldExample(
        id="ex25_smoking_cessation",
        modality="text",
        input=(
            "Smoking cessation visit. 32 pack-year history, smoked 1 PPD x 15 years, currently "
            "reducing to half a pack daily. Started varenicline 1mg BID 1 week ago. No SI, mild nausea. "
            "BP 128/82, HR 80."
        ),
        gold={
            "diagnoses": [{"condition": "Tobacco use disorder", "icd10": "F17.210", "status": "active"}],
            "medications": [{"name": "Varenicline", "dose": "1mg", "frequency": "BID"}],
            "vitals": [
                {"type": "bp", "value": "128/82", "unit": "mmHg"},
                {"type": "hr", "value": "80", "unit": "bpm"},
            ],
            "labs": [],
            "symptoms": [{"description": "Mild nausea", "severity": "mild"}],
            "red_flags": [],
        },
        tags=["text", "easy", "prevention"],
    ),
    GoldExample(
        id="ex26_sleep_apnea",
        modality="pdf",
        input=(
            "SLEEP STUDY (POLYSOMNOGRAPHY) 2026-01-15\n"
            "Total sleep time: 6.2 h\n"
            "AHI: 28 events/h (severe)\n"
            "Lowest SpO2: 82%\n"
            "Time below 90% SpO2: 24 min\n"
            "IMPRESSION: Severe obstructive sleep apnea. CPAP recommended."
        ),
        gold={
            "diagnoses": [{"condition": "Obstructive sleep apnea, severe", "icd10": "G47.33", "status": "active"}],
            "medications": [], "vitals": [],
            "labs": [
                {"test": "AHI", "value": "28", "unit": "events/h", "flag": "high"},
                {"test": "Lowest SpO2", "value": "82", "unit": "%", "flag": "low"},
            ],
            "symptoms": [], "red_flags": [],
        },
        tags=["pdf", "medium", "sleep"],
    ),
    GoldExample(
        id="ex27_vision_loss_voice",
        modality="voice",
        input=(
            "Voice note. About 30 minutes ago I suddenly lost vision in my right eye — like a curtain "
            "came down. No pain. No headache. I'm 62 with high blood pressure."
        ),
        gold={
            "diagnoses": [],
            "medications": [], "vitals": [], "labs": [],
            "symptoms": [
                {"description": "Sudden painless monocular vision loss, right eye, 'curtain' pattern", "onset": "30 min", "severity": "severe"},
            ],
            "red_flags": [
                {"finding": "Acute monocular vision loss — concern for retinal artery occlusion or amaurosis fugax", "urgency": "emergent"},
            ],
        },
        tags=["voice", "hard", "emergency", "ophtho"],
    ),
    GoldExample(
        id="ex28_pneumonia_chest_xray",
        modality="pdf",
        input=(
            "CHEST X-RAY  PA + LATERAL  2026-04-30\n"
            "INDICATION: Cough, fever.\n"
            "FINDINGS: Patchy opacity right lower lobe consistent with pneumonia. "
            "No effusion. Cardiac silhouette normal. No pneumothorax.\n"
            "IMPRESSION: Right lower lobe pneumonia."
        ),
        gold={
            "diagnoses": [{"condition": "Right lower lobe pneumonia", "icd10": "J18.1", "status": "active"}],
            "medications": [], "vitals": [], "labs": [],
            "symptoms": [
                {"description": "Cough and fever", "severity": "moderate"},
            ],
            "red_flags": [],
        },
        tags=["pdf", "easy", "imaging"],
    ),
    GoldExample(
        id="ex29_pregnancy_routine",
        modality="text",
        input=(
            "OB visit at 28 weeks GA. Fundal height 28cm. Fetal heart tones 148 bpm. "
            "BP 118/76. No edema, no headache, no visual changes. 1-hour glucose challenge 132 mg/dL "
            "(normal). Continuing prenatal vitamin + iron 65mg QD."
        ),
        gold={
            "diagnoses": [{"condition": "Pregnancy, 28 weeks gestation", "icd10": "Z3A.28", "status": "active"}],
            "medications": [
                {"name": "Prenatal vitamin", "dose": "", "frequency": "QD"},
                {"name": "Iron", "dose": "65mg", "frequency": "QD"},
            ],
            "vitals": [
                {"type": "bp", "value": "118/76", "unit": "mmHg"},
                {"type": "hr", "value": "148", "unit": "bpm"},
            ],
            "labs": [
                {"test": "1-hour glucose challenge", "value": "132", "unit": "mg/dL", "flag": "normal"},
            ],
            "symptoms": [], "red_flags": [],
        },
        tags=["text", "medium", "obgyn"],
    ),
    GoldExample(
        id="ex30_chronic_kidney",
        modality="pdf",
        input=(
            "Nephrology visit. CKD stage 3a (eGFR 52). Cr 1.4 (stable from 1.3). "
            "Urine ACR 145 mg/g (moderately increased). On lisinopril 20mg QD for BP + renoprotection. "
            "K+ 4.6, bicarb 24. No edema. BP 132/80."
        ),
        gold={
            "diagnoses": [{"condition": "Chronic kidney disease stage 3a", "icd10": "N18.31", "status": "active"}],
            "medications": [{"name": "Lisinopril", "dose": "20mg", "frequency": "QD"}],
            "vitals": [{"type": "bp", "value": "132/80", "unit": "mmHg"}],
            "labs": [
                {"test": "eGFR", "value": "52", "unit": "mL/min", "flag": "low"},
                {"test": "Creatinine", "value": "1.4", "unit": "mg/dL", "flag": "high"},
                {"test": "Urine ACR", "value": "145", "unit": "mg/g", "flag": "high"},
                {"test": "Potassium", "value": "4.6", "unit": "mEq/L", "flag": "normal"},
                {"test": "Bicarbonate", "value": "24", "unit": "mEq/L", "flag": "normal"},
            ],
            "symptoms": [], "red_flags": [],
        },
        tags=["pdf", "hard", "nephrology"],
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
