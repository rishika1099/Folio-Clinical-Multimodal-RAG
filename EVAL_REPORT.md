# Folio — Evaluation Report

_Generated 2026-05-27T04:04:35.328143Z · 12 extraction examples · 10 RAG queries · 6 PII cases · 3 chat probes_

This report runs the eval harness against a fixed synthetic gold dataset. All metrics are reproducible — `python -m app.eval.runner` regenerates this file.

## Headline numbers

| Area | Metric | Value |
|---|---|---|
| Extraction | Micro-F1 (all sections) | **94.7%** |
| Extraction | Macro-F1 (mean across sections) | **95.8%** |
| Extraction | Schema validity | 100.0% |
| Extraction | Hallucination rate | 1.2% |
| Extraction | Coverage of gold items | 94.0% |
| RAG | Recall@1 | **30.0%** |
| RAG | Recall@5 | 50.0% |
| RAG | MRR | 0.407 |
| RAG | NDCG@10 | 0.538 |
| Consensus | Unanimous agreement (3/3) | 40.8% |
| Consensus | Convergence (≥2/3) | 85.7% |
| Consensus | Cluster representative correctness | 100.0% |
| Consensus | Recall lift over single-model average | +10.2% |
| PII | Scrub recall | **100.0%** |
| PII | Content preservation | 100.0% |
| Chat | Answer correctness | 100.0% |
| Chat | Citation correctness | 100.0% |
| Chat | Red-flag detection recall | 100.0% |
| Chat | Hallucination guard | 100.0% |
| Latency | PII scrub p50 / p95 | 0.038 ms / 0.039 ms |
| Latency | Hash-embed p50 (per doc) | 0.068 ms |
| Latency | Cosine search p50 over corpus | 0.943 ms |

## 1. Extraction quality

Per-section precision / recall / F1, aggregated across the gold corpus. Items are matched on canonical keys (condition name, drug name, vital type, lab test name, first words of symptom / red-flag description) so formatting variants count as a match.

| Section | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| diagnoses | 5 | 0 | 0 | 100.0% | 100.0% | **100.0%** |
| medications | 12 | 1 | 0 | 92.3% | 100.0% | **96.0%** |
| vitals | 11 | 0 | 2 | 100.0% | 84.6% | **91.7%** |
| labs | 9 | 0 | 1 | 100.0% | 90.0% | **94.7%** |
| symptoms | 6 | 0 | 1 | 100.0% | 85.7% | **92.3%** |
| red_flags | 2 | 0 | 0 | 100.0% | 100.0% | **100.0%** |

### By modality

| Modality | N | Macro-F1 |
|---|---:|---:|
| text | 6 | 99.5% |
| pdf | 3 | 98.1% |
| voice | 2 | 97.2% |
| image | 1 | 100.0% |

### By difficulty

| Tag | N | Macro-F1 |
|---|---:|---:|
| easy | 4 | 100.0% |
| medium | 4 | 99.2% |
| hard | 4 | 97.2% |

## 2. RAG retrieval

Top-k retrieval over the gold corpus for each canonical query. Embeddings are deterministic hash-bag pseudo-embeddings (live API replaces these in production).

| Metric | Value |
|---|---:|
| Recall@1 | 30.0% |
| Recall@3 | 30.0% |
| Recall@5 | 50.0% |
| Recall@10 | 100.0% |
| MRR | 0.407 |
| NDCG@10 | 0.538 |
| Mean embed time per query | 0.05 ms |
| Mean cosine search time per query | 0.914 ms |

### Per-query top-5

| Query | First-hit rank | Top-5 returned |
|---|---:|---|
| When was my last A1C and what was it? | 10 | `ex10, ex05, ex08, ex04, ex01` |
| Is my blood pressure trending up? | 4 | `ex05, ex03, ex10, ex01, ex02` |
| What medications am I on for diabetes? | 4 | `ex05, ex12, ex03, ex07, ex01` |
| Have I had a stroke or stroke symptoms? | 10 | `ex01, ex02, ex03, ex04, ex05` |
| Tell me about my thyroid labs. | 9 | `ex10, ex05, ex06, ex11, ex08` |
| What's the skin lesion on my arm? | 1 | `ex06, ex05, ex08, ex12, ex01` |
| Was I hospitalised recently? | 9 | `ex12, ex01, ex02, ex03, ex04` |
| Am I on warfarin? | 7 | `ex02, ex01, ex03, ex04, ex05` |
| Should I worry about chest pain? | 1 | `ex03, ex10, ex02, ex01, ex04` |
| What's my cancer treatment plan? | 1 | `ex12, ex06, ex05, ex01, ex02` |

## 3. Multi-LLM consensus

Three simulated models (Anthropic / OpenAI / Gemini perturbations of gold) are passed through the same field-level clustering + voting pipeline used in production. This benchmarks the *consensus algorithm*, not the underlying models — running against live models requires API budget.

| Metric | Value |
|---|---:|
| Unanimous agreement (3/3 models had item) | 40.8% |
| Convergence (≥2/3 had item — what consensus keeps) | 85.7% |
| Cluster representative matches gold | 100.0% |
| Mean single-model recall (across 3 models) | 75.5% |
| Consensus recall | **85.7%** |
| Lift vs single-model average | +10.2% |
| Fleiss' κ (raw, for reference) | -0.067 |
| Input-token cost ratio (consensus vs single) | 3.0× |

> **Note on Fleiss κ.** For this synthetic perturbation scheme (model 0 drops last, model 1 drops first, model 2 perfect) the κ can read slightly negative because the disagreements happen systematically rather than at random — the formula penalises structured disagreement. The actionable numbers are convergence rate and consensus recall lift, both shown above.

## 4. PII scrubbing

Tested across **6** canonical PII cases covering SSN, MRN, email, phone, DOB, plus a clean-input control. Coverage broken out by class:

| Class | Cases | Recall |
|---|---:|---:|
| SSN | 2 | 100.0% |
| MRN | 2 | 100.0% |
| DOB | 1 | 100.0% |
| Email | 2 | 100.0% |
| Phone | 3 | 100.0% |

- **Total scrub recall**: 100.0%
- **Content preservation** (clinical info kept intact): 100.0%

## 5. Latency

Sampled n=50 runs per stage on local hardware.

| Stage | Mean | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| PII scrub | 0.038 ms | 0.038 ms | 0.039 ms | 0.040 ms |
| Hash embed (per doc) | 0.068 ms | 0.068 ms | 0.070 ms | 0.071 ms |
| Cosine search (full corpus) | 0.939 ms | 0.943 ms | 0.979 ms | 0.985 ms |

## 6. Chat groundedness

Probes the chat path with canned questions whose factually correct answers live in the gold corpus. Synthesised reference replies stand in when no Anthropic key is configured; live runs would substitute real model outputs.

| Metric | Value |
|---|---:|
| Answer correctness (key term present) | 100.0% |
| Citation correctness (right reports cited) | 100.0% |
| Red-flag escalation recall | 100.0% |
| Hallucination guard (forbidden strings absent) | 100.0% |

---

**Reproducing this report**

```bash
docker compose exec backend python -m app.eval.runner
# Add --live-embed to use the real OpenAI embedding endpoint
# Add --json out.json to also write machine-readable results
```

Synthetic eval data is hand-authored in `backend/app/eval/dataset.py` and deliberately covers easy / medium / hard cases across all four input modalities, plus emergency red-flag scenarios.