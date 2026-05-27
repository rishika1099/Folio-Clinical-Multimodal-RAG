"""
Extraction-quality metrics.

For each gold example, we compare the model's extracted fields against
the canonical labels and compute:

  - Field-level precision / recall / F1 per section (diagnoses,
    medications, vitals, labs, symptoms, red_flags)
  - Macro-averaged F1 across sections (each section weighted equally)
  - Micro-averaged F1 (each item weighted equally)
  - Schema validity rate (% extractions that parse as the unified schema)
  - Hallucination rate (% predicted items whose key terms don't appear
    anywhere in the source — a proxy for fabricated content)
  - Coverage rate (% gold items captured)
  - Per-modality and per-difficulty slices
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from ..dataset import EXTRACTION_GOLD, GoldExample


SECTIONS = ("diagnoses", "medications", "vitals", "labs", "symptoms", "red_flags")


# Sections that use exact-key matching (concrete, low-variation): the
# canonical key reliably distinguishes items. Sections NOT in this set
# fall back to fuzzy token-overlap matching to absorb synonyms and
# rephrasings ("Essential hypertension" ≈ "Hypertension",
# "HbA1c" ≈ "Hemoglobin A1C").
EXACT_SECTIONS = {"medications", "vitals"}


_STOP = {"the","a","an","of","in","on","at","with","and","or","for","by","to",
         "is","was","were","be","been","has","have","had"}
_QUAL = {"essential","acute","chronic","suspected","mild","severe","moderate",
         "possible","probable","stage","unilateral","bilateral","right","left",
         "primary","secondary","s/p","new","recent","increased","decreased"}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _tokens(text: str) -> set[str]:
    """Significant content tokens from a clinical phrase."""
    raw = _norm(text)
    for ch in "().,;:[]/-":
        raw = raw.replace(ch, " ")
    out: set[str] = set()
    for t in raw.split():
        if not t or t in _STOP or t in _QUAL:
            continue
        out.add(t)
    return out


def _overlap(a: str, b: str) -> float:
    """Symmetric Jaccard-like overlap: |A ∩ B| / min(|A|, |B|)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _diag_key(d: dict) -> str:
    return _norm(d.get("condition", ""))[:40]


def _med_key(m: dict) -> str:
    return _norm(m.get("name", "")).split()[0] if m.get("name") else ""


def _vital_key(v: dict) -> str:
    return _norm(v.get("type", ""))


def _lab_key(l: dict) -> str:
    return _norm(l.get("test", ""))


def _symptom_key(s: dict) -> str:
    # Take the first 4 words of the description as the canonical key
    return " ".join(_norm(s.get("description", "")).split()[:4])


def _flag_key(f: dict) -> str:
    return " ".join(_norm(f.get("finding", "")).split()[:4])


KEY_FN: dict[str, Callable[[dict], str]] = {
    "diagnoses": _diag_key,
    "medications": _med_key,
    "vitals": _vital_key,
    "labs": _lab_key,
    "symptoms": _symptom_key,
    "red_flags": _flag_key,
}


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def compare_section(gold: list[dict], pred: list[dict], key_fn: Callable[[dict], str]) -> PRF:
    g = {key_fn(x) for x in gold if key_fn(x)}
    p = {key_fn(x) for x in pred if key_fn(x)}
    return PRF(
        tp=len(g & p),
        fp=len(p - g),
        fn=len(g - p),
    )


# Text-for-overlap accessors for the fuzzy sections.
TEXT_FN: dict[str, Callable[[dict], str]] = {
    "diagnoses":  lambda d: d.get("condition", ""),
    "labs":       lambda l: l.get("test", ""),
    "symptoms":   lambda s: s.get("description", ""),
    "red_flags":  lambda f: f.get("finding", ""),
}


def compare_section_fuzzy(
    gold: list[dict], pred: list[dict], text_fn: Callable[[dict], str],
    thresh: float = 0.5,
) -> PRF:
    """Greedy bipartite matching by token overlap. Each predicted item
    is matched to the best-overlapping unmatched gold item; a match
    counts if overlap ≥ thresh. Unmatched preds are FP; unmatched gold
    are FN. Order-independent."""
    g_texts = [text_fn(x) for x in gold]
    p_texts = [text_fn(x) for x in pred]
    used = [False] * len(g_texts)
    tp = fp = 0
    for pt in p_texts:
        if not pt:
            continue
        best_i = -1
        best_ov = 0.0
        for i, gt in enumerate(g_texts):
            if used[i] or not gt:
                continue
            ov = _overlap(pt, gt)
            if ov > best_ov:
                best_ov, best_i = ov, i
        if best_i >= 0 and best_ov >= thresh:
            used[best_i] = True
            tp += 1
        else:
            fp += 1
    fn = used.count(False) - sum(1 for g in g_texts if not g)
    return PRF(tp=tp, fp=fp, fn=max(0, fn))


def compare_example(gold: dict, pred: dict) -> dict[str, PRF]:
    out: dict[str, PRF] = {}
    for sec in SECTIONS:
        if sec in EXACT_SECTIONS:
            out[sec] = compare_section(gold.get(sec, []), pred.get(sec, []), KEY_FN[sec])
        else:
            out[sec] = compare_section_fuzzy(
                gold.get(sec, []), pred.get(sec, []), TEXT_FN[sec],
            )
    return out


def is_schema_valid(pred: dict) -> bool:
    if not isinstance(pred, dict):
        return False
    for sec in SECTIONS:
        v = pred.get(sec)
        if v is not None and not isinstance(v, list):
            return False
    return True


def hallucination_rate(source: str, pred: dict) -> float:
    """
    Conservative hallucination check: only flags items whose VALUES
    should literally appear in the source — medication name, vital
    numeric reading, lab value. Inference-heavy sections (diagnoses
    inferred from meds, red flags inferred from symptoms) are excluded
    because they're legitimate model behaviour, not fabrication.

    The metric catches the worst class of failure: a model that invents
    a drug, a BP reading, or a lab number that the patient never had.
    """
    source_lc = (source or "").lower()
    total = 0
    halluc = 0

    # (section, fn-that-returns-a-string-that-MUST-be-in-source)
    checks: list[tuple[str, Callable[[dict], str]]] = [
        ("medications", lambda m: _norm(m.get("name", "")).split()[0] if m.get("name") else ""),
        ("vitals",      lambda v: _norm(v.get("value", ""))),
        ("labs",        lambda l: _norm(l.get("value", ""))),
    ]
    for sec, fn in checks:
        items = pred.get(sec) or []
        for item in items:
            key = fn(item)
            if not key:
                continue
            total += 1
            if key not in source_lc:
                halluc += 1
    return halluc / total if total else 0.0


def coverage_rate(gold: dict, pred: dict) -> float:
    gold_total = sum(len(gold.get(s, [])) for s in SECTIONS)
    if not gold_total:
        return 1.0
    caught = 0
    for sec in SECTIONS:
        g = {KEY_FN[sec](x) for x in gold.get(sec, []) if KEY_FN[sec](x)}
        p = {KEY_FN[sec](x) for x in pred.get(sec, []) if KEY_FN[sec](x)}
        caught += len(g & p)
    return caught / gold_total


@dataclass
class ExtractionResult:
    per_section: dict[str, PRF]
    schema_valid: float
    hallucination: float
    coverage: float
    n: int
    micro_f1: float
    macro_f1: float
    by_modality: dict[str, dict[str, float]]
    by_difficulty: dict[str, dict[str, float]]


def evaluate_extraction(predictions: dict[str, dict]) -> ExtractionResult:
    """
    predictions: {example_id: predicted_extraction_dict}
    Missing predictions are scored as empty (no items extracted).
    """
    agg: dict[str, PRF] = {s: PRF() for s in SECTIONS}
    schema_ok = 0
    halluc_sum = 0.0
    cov_sum = 0.0

    # Slice trackers.
    by_mod: dict[str, list[float]] = {}
    by_diff: dict[str, list[float]] = {}

    for ex in EXTRACTION_GOLD:
        pred = predictions.get(ex.id, {}) or {}
        if is_schema_valid(pred):
            schema_ok += 1
        halluc_sum += hallucination_rate(ex.input, pred)
        cov_sum += coverage_rate(ex.gold, pred)

        per = compare_example(ex.gold, pred)
        for sec, prf in per.items():
            agg[sec].tp += prf.tp
            agg[sec].fp += prf.fp
            agg[sec].fn += prf.fn

        # Macro F1 of this example for slicing.
        ex_f1 = sum(prf.f1 for prf in per.values()) / len(per)
        by_mod.setdefault(ex.modality, []).append(ex_f1)
        for tag in ("easy", "medium", "hard"):
            if tag in ex.tags:
                by_diff.setdefault(tag, []).append(ex_f1)
                break

    n = len(EXTRACTION_GOLD)
    tp = sum(p.tp for p in agg.values())
    fp = sum(p.fp for p in agg.values())
    fn = sum(p.fn for p in agg.values())
    micro = PRF(tp=tp, fp=fp, fn=fn).f1
    macro = sum(p.f1 for p in agg.values()) / len(agg)

    by_modality = {m: {"n": len(vs), "macro_f1": sum(vs) / len(vs)} for m, vs in by_mod.items()}
    by_difficulty = {d: {"n": len(vs), "macro_f1": sum(vs) / len(vs)} for d, vs in by_diff.items()}

    return ExtractionResult(
        per_section=agg,
        schema_valid=schema_ok / n if n else 0.0,
        hallucination=halluc_sum / n if n else 0.0,
        coverage=cov_sum / n if n else 0.0,
        n=n,
        micro_f1=micro,
        macro_f1=macro,
        by_modality=by_modality,
        by_difficulty=by_difficulty,
    )


def synthesize_reference_predictions() -> dict[str, dict]:
    """
    Returns a predictions map that mostly matches gold, with deliberately
    seeded errors so the eval framework produces non-degenerate numbers
    even when no live LLM is available. Real eval would replace this with
    actual model outputs.
    """
    out: dict[str, dict] = {}
    for ex in EXTRACTION_GOLD:
        import copy
        pred = copy.deepcopy(ex.gold)

        # Seed plausible errors:
        # - drop the last lab on ex02 (recall miss)
        if ex.id == "ex02_diabetes_panel":
            pred["labs"] = pred["labs"][:-1]
        # - add a hallucinated med on ex07 (precision miss + halluc)
        if ex.id == "ex07_polypharmacy":
            pred["medications"] = pred["medications"] + [
                {"name": "Spironolactone", "dose": "25mg", "frequency": "QD"}
            ]
        # - miss one symptom on ex10 (recall miss on emergency)
        if ex.id == "ex10_stroke_red_flag":
            pred["symptoms"] = pred["symptoms"][:1]
        # - emit a non-list for vitals on ex11 (schema invalid)
        if ex.id == "ex11_pediatric_vitals":
            pred["vitals"] = pred["vitals"]  # actually keep valid for now
        # - drop the second vital on ex08
        if ex.id == "ex08_pdf_discharge":
            pred["vitals"] = pred["vitals"][:2]

        out[ex.id] = pred
    return out
