"""
Drug-interaction precision/recall against the curated DB.

Validates the "we don't use the LLM for this" architectural claim with
numbers. Each gold case has a med list + the set of interaction pairs
that should flag. We run the curated-DB lookup (the same code path
production uses in suggestions/interactions.py) and score it.
"""
from __future__ import annotations
from dataclasses import dataclass

from ...suggestions.interactions import detect_interactions
from ..dataset import INTERACTION_GOLD


def _canon(pair: tuple[str, str, str] | tuple[str, str]) -> frozenset:
    # Treat (a, b) and (b, a) as the same pair.
    return frozenset(pair[:2])


@dataclass
class InteractionResult:
    n_cases: int
    n_total_pairs_expected: int
    n_total_pairs_predicted: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    accuracy: float       # % cases where predicted set == expected set
    per_case: list[dict]


def evaluate_interactions() -> InteractionResult:
    tp = fp = fn = 0
    correct = 0
    per_case: list[dict] = []

    for case in INTERACTION_GOLD:
        pred_triples = detect_interactions(case.meds)
        pred_pairs = {_canon(t) for t in pred_triples}
        gold_pairs = {_canon(p) for p in case.expected}

        case_tp = len(gold_pairs & pred_pairs)
        case_fp = len(pred_pairs - gold_pairs)
        case_fn = len(gold_pairs - pred_pairs)
        tp += case_tp; fp += case_fp; fn += case_fn

        is_exact = (pred_pairs == gold_pairs)
        if is_exact:
            correct += 1

        per_case.append({
            "meds":     case.meds,
            "expected": sorted(["+".join(sorted(p)) for p in gold_pairs]),
            "predicted": sorted(["+".join(sorted(p)) for p in pred_pairs]),
            "ok": is_exact,
            "note": case.note,
        })

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall    = tp / (tp + fn) if (tp + fn) else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return InteractionResult(
        n_cases=len(INTERACTION_GOLD),
        n_total_pairs_expected=sum(len(c.expected) for c in INTERACTION_GOLD),
        n_total_pairs_predicted=sum(len(detect_interactions(c.meds)) for c in INTERACTION_GOLD),
        tp=tp, fp=fp, fn=fn,
        precision=precision, recall=recall, f1=f1,
        accuracy=correct / len(INTERACTION_GOLD) if INTERACTION_GOLD else 1.0,
        per_case=per_case,
    )
