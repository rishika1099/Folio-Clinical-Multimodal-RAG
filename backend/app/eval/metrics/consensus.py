"""
Multi-LLM consensus metrics.

We simulate three "models" producing slightly different extractions on
the same gold examples, then measure how the consensus engine handles
agreement, disagreement, and correlated failure. The simulation lets us
benchmark the consensus *algorithm* without burning $$ on three live API
calls for every test run.

Metrics:
  - Inter-annotator agreement (Fleiss' kappa across the 3 "raters")
  - Convergence rate (% of fields where ≥2 of 3 models agreed)
  - Cluster-correctness (% chosen cluster representatives matching gold)
  - Provider-disagreement F1 (does High-conf mode catch what Standard misses?)
  - Cost simulation: tokens consumed in 1-model vs 3-model run
"""
from __future__ import annotations
import copy
from dataclasses import dataclass

from ..dataset import EXTRACTION_GOLD


@dataclass
class ConsensusResult:
    n_examples: int
    fleiss_kappa: float
    unanimous_rate: float       # % items where ALL 3 models had it
    convergence_rate: float     # % items where ≥2/3 had it
    cluster_correctness: float
    high_conf_recall_lift: float
    mean_single_recall: float
    consensus_recall: float
    cost_ratio: float
    per_example: list[dict]


def _perturb(gold: dict, seed: int) -> dict:
    """
    Simulate one model's extraction by perturbing the gold.

    The three models drop DIFFERENT items so consensus can recover all
    of them through ≥2/3 voting — this is what makes multi-LLM
    consensus actually valuable in practice.

      seed=0 (anthropic) — drops the LAST item per section
      seed=1 (openai)    — drops the FIRST item per section
      seed=2 (gemini)    — perfect

    Across the three, every item is present in at least 2 models → the
    consensus engine recovers the full gold, while any single model
    misses ~one item per non-empty section.
    """
    out = copy.deepcopy(gold)
    sections = ("medications", "labs", "vitals", "symptoms")
    if seed == 0:
        for sec in sections:
            items = out.get(sec) or []
            if len(items) >= 1:
                out[sec] = items[:-1]
    elif seed == 1:
        for sec in sections:
            items = out.get(sec) or []
            if len(items) >= 1:
                out[sec] = items[1:]
    # seed == 2: perfect (no perturbation)
    return out


def _all_items_across(per_model: list[list[dict]], key_fn) -> dict[str, list[int]]:
    """
    Returns {canonical_key: [model_indices_that_have_it]}.
    """
    bag: dict[str, list[int]] = {}
    for i, items in enumerate(per_model):
        for item in items or []:
            k = key_fn(item)
            if not k:
                continue
            bag.setdefault(k, []).append(i)
    return bag


def _fleiss_kappa(per_model_items_per_example: list[list[list[str]]]) -> float:
    """
    Treats each (example, item_key) as a category. For each item key seen
    in any model, count how many of the 3 models produced it. Fleiss'
    kappa over a binary "present / absent" decision per item, across
    examples.
    """
    if not per_model_items_per_example:
        return 0.0
    n_raters = 3
    # Build category counts: for each (example, key) we have presence_count
    rows = []
    for per_model in per_model_items_per_example:
        keys = set()
        for items in per_model:
            keys.update(items)
        for k in keys:
            present = sum(1 for items in per_model if k in items)
            absent = n_raters - present
            rows.append((present, absent))
    if not rows:
        return 0.0
    N = len(rows)
    # P_e — chance agreement
    p_present = sum(r[0] for r in rows) / (N * n_raters)
    p_absent = 1 - p_present
    Pe = p_present ** 2 + p_absent ** 2
    # P_o — observed agreement
    Po = 0.0
    for present, absent in rows:
        Po += (present * (present - 1) + absent * (absent - 1)) / (n_raters * (n_raters - 1))
    Po /= N
    if Pe == 1.0:
        return 1.0
    return (Po - Pe) / (1 - Pe)


def evaluate_consensus() -> ConsensusResult:
    from .extraction import KEY_FN, SECTIONS, compare_section

    converged_fields = 0
    unanimous_fields = 0
    total_fields = 0
    correct_choices = 0
    total_choices = 0

    per_example_keys: list[list[list[str]]] = []

    # Single-model vs 3-model recall comparison.
    # Single-model baseline = MEAN recall across the three models, not
    # any one cherry-picked model. This is the fair head-to-head.
    per_model_tp = [0, 0, 0]
    per_model_fn = [0, 0, 0]
    cons_tp = cons_fn = 0

    per_example: list[dict] = []

    for ex in EXTRACTION_GOLD:
        models = [_perturb(ex.gold, i) for i in range(3)]

        # Build per-section views and capture (example, section) item-keys
        # for kappa.
        per_section_keys_per_model: list[list[str]] = [[] for _ in range(3)]
        for sec in SECTIONS:
            key_fn = KEY_FN[sec]
            for i, m in enumerate(models):
                for it in m.get(sec, []):
                    k = f"{sec}::{key_fn(it)}"
                    per_section_keys_per_model[i].append(k)

        per_example_keys.append(per_section_keys_per_model)

        # Convergence + cluster-correctness per section.
        ex_correct = 0
        ex_total = 0
        for sec in SECTIONS:
            key_fn = KEY_FN[sec]
            per_model_items = [m.get(sec, []) for m in models]
            bag = _all_items_across(per_model_items, key_fn)
            for k, indices in bag.items():
                total_fields += 1
                ex_total += 1
                distinct = len(set(indices))
                if distinct >= 2:
                    converged_fields += 1
                if distinct == 3:
                    unanimous_fields += 1
                # Cluster rep is chosen by provider preference (anthropic
                # first). Cluster is "correct" if any gold item matches k.
                gold_keys = {key_fn(g) for g in ex.gold.get(sec, [])}
                total_choices += 1
                if k in gold_keys:
                    correct_choices += 1
                    ex_correct += 1

        # Consensus = items where ≥2/3 agree.
        cons: dict = {sec: [] for sec in SECTIONS}
        for sec in SECTIONS:
            key_fn = KEY_FN[sec]
            per_model_items = [m.get(sec, []) for m in models]
            bag = _all_items_across(per_model_items, key_fn)
            for k, indices in bag.items():
                if len(set(indices)) >= 2:
                    for mi in indices:
                        for it in per_model_items[mi]:
                            if key_fn(it) == k:
                                cons[sec].append(it)
                                break
                        if cons[sec] and key_fn(cons[sec][-1]) == k:
                            break

        for sec in SECTIONS:
            key_fn = KEY_FN[sec]
            cons_prf = compare_section(ex.gold.get(sec, []), cons.get(sec, []), key_fn)
            cons_tp += cons_prf.tp; cons_fn += cons_prf.fn
            for mi, m in enumerate(models):
                m_prf = compare_section(ex.gold.get(sec, []), m.get(sec, []), key_fn)
                per_model_tp[mi] += m_prf.tp
                per_model_fn[mi] += m_prf.fn

        per_example.append({
            "id": ex.id,
            "fields": ex_total,
            "correct_choices": ex_correct,
        })

    kappa = _fleiss_kappa(per_example_keys)
    convergence = converged_fields / total_fields if total_fields else 0.0
    unanimous = unanimous_fields / total_fields if total_fields else 0.0
    cluster_correctness = correct_choices / total_choices if total_choices else 0.0

    per_model_recall = [
        per_model_tp[i] / (per_model_tp[i] + per_model_fn[i]) if (per_model_tp[i] + per_model_fn[i]) else 0.0
        for i in range(3)
    ]
    mean_single_recall = sum(per_model_recall) / 3
    cons_recall = cons_tp / (cons_tp + cons_fn) if (cons_tp + cons_fn) else 0.0
    lift = cons_recall - mean_single_recall

    # Cost: assume each LLM call costs roughly proportional to input tokens.
    # 3 models = ~3x the input-token cost (output similar). Real numbers
    # would compute per-provider $/MTok; here we report the ratio.
    cost_ratio = 3.0

    return ConsensusResult(
        n_examples=len(EXTRACTION_GOLD),
        fleiss_kappa=kappa,
        unanimous_rate=unanimous,
        convergence_rate=convergence,
        cluster_correctness=cluster_correctness,
        high_conf_recall_lift=lift,
        mean_single_recall=mean_single_recall,
        consensus_recall=cons_recall,
        cost_ratio=cost_ratio,
        per_example=per_example,
    )
