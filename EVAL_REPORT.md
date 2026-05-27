# Folio — Evaluation Report

_Generated 2026-05-27T13:04:50.459800Z · 30 extraction examples · 10 RAG queries · 6 PII cases · 3 chat probes_

**Extraction predictions: LIVE** — `claude-haiku-4-5` on 30 examples (24,566 input + 11,381 output tokens).

All metrics are reproducible — `python -m app.eval.runner` regenerates this file.

## Headline numbers

| Area | Metric | Value |
|---|---|---|
| Extraction | Micro-F1 (all sections) | **83.7%** |
| Extraction | Macro-F1 (mean across sections) | **84.2%** |
| Extraction | Schema validity | 100.0% |
| Extraction | Hallucination rate | 13.1% |
| Extraction | Coverage of gold items | 91.8% |
| RAG | Recall@1 | **100.0%** |
| RAG | Recall@5 | 100.0% |
| RAG | MRR | 1.000 |
| RAG | NDCG@10 | 0.970 |
| Consensus | Unanimous agreement (3/3) | 36.6% |
| Consensus | Convergence (≥2/3) | 79.4% |
| Consensus | Cluster representative correctness | 100.0% |
| Consensus | Recall lift over single-model average | +7.4% |
| PII | Scrub recall | **100.0%** |
| PII | Content preservation | 100.0% |
| Chat | Answer correctness | 100.0% |
| Chat | Citation correctness | 100.0% |
| Chat | Red-flag detection recall | 100.0% |
| Chat | Hallucination guard | 100.0% |
| Latency | PII scrub p50 / p95 | 0.065 ms / 0.081 ms |
| Latency | Hash-embed p50 (per doc) | 0.074 ms |
| Latency | Cosine search p50 over corpus | 2.314 ms |

## 1. Extraction quality

Per-section precision / recall / F1, aggregated across the gold corpus. Items are matched on canonical keys (condition name, drug name, vital type, lab test name, first words of symptom / red-flag description) so formatting variants count as a match.

| Section | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| diagnoses | 21 | 10 | 2 | 67.7% | 91.3% | **77.8%** |
| medications | 29 | 3 | 2 | 90.6% | 93.5% | **92.1%** |
| vitals | 22 | 1 | 0 | 95.7% | 100.0% | **97.8%** |
| labs | 31 | 9 | 2 | 77.5% | 93.9% | **84.9%** |
| symptoms | 16 | 16 | 2 | 50.0% | 88.9% | **64.0%** |
| red_flags | 4 | 1 | 0 | 80.0% | 100.0% | **88.9%** |

### By modality

| Modality | N | Macro-F1 |
|---|---:|---:|
| text | 14 | 88.7% |
| pdf | 10 | 89.1% |
| voice | 5 | 79.8% |
| image | 1 | 83.3% |

### By difficulty

| Tag | N | Macro-F1 |
|---|---:|---:|
| easy | 9 | 90.7% |
| medium | 13 | 86.3% |
| hard | 8 | 84.6% |

## 2. RAG retrieval

Top-k retrieval over the gold corpus for each canonical query. Embeddings are **live (OpenAI text-embedding-3-small)**.

| Metric | Value |
|---|---:|
| Recall@1 | 100.0% |
| Recall@3 | 100.0% |
| Recall@5 | 100.0% |
| Recall@10 | 100.0% |
| MRR | 1.000 |
| NDCG@10 | 0.970 |
| Mean embed time per query | 685.14 ms |
| Mean cosine search time per query | 5.800 ms |

### Per-query top-5

| Query | First-hit rank | Top-5 returned |
|---|---:|---|
| When was my last A1C and what was it? | 1 | `ex02, ex21, ex29, ex01, ex30` |
| Is my blood pressure trending up? | 1 | `ex01, ex14, ex02, ex30, ex03` |
| What medications am I on for diabetes? | 1 | `ex02, ex07, ex14, ex01, ex30` |
| Have I had a stroke or stroke symptoms? | 1 | `ex10, ex27, ex03, ex05, ex19` |
| Tell me about my thyroid labs. | 1 | `ex04, ex13, ex21, ex02, ex11` |
| What's the skin lesion on my arm? | 1 | `ex06, ex03, ex12, ex28, ex22` |
| Was I hospitalised recently? | 1 | `ex08, ex20, ex28, ex03, ex27` |
| Am I on warfarin? | 1 | `ex07, ex25, ex21, ex23, ex01` |
| Should I worry about chest pain? | 1 | `ex03, ex28, ex15, ex18, ex22` |
| What's my cancer treatment plan? | 1 | `ex12, ex02, ex07, ex08, ex20` |

## 3. Multi-LLM consensus

Three simulated models (Anthropic / OpenAI / Gemini perturbations of gold) are passed through the same field-level clustering + voting pipeline used in production. This benchmarks the *consensus algorithm*, not the underlying models — running against live models requires API budget.

| Metric | Value |
|---|---:|
| Unanimous agreement (3/3 models had item) | 36.6% |
| Convergence (≥2/3 had item — what consensus keeps) | 79.4% |
| Cluster representative matches gold | 100.0% |
| Mean single-model recall (across 3 models) | 72.0% |
| Consensus recall | **79.4%** |
| Lift vs single-model average | +7.4% |
| Fleiss' κ (raw, for reference) | -0.048 |
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
| PII scrub | 0.067 ms | 0.065 ms | 0.081 ms | 0.082 ms |
| Hash embed (per doc) | 0.077 ms | 0.074 ms | 0.097 ms | 0.106 ms |
| Cosine search (full corpus) | 2.329 ms | 2.314 ms | 2.473 ms | 2.496 ms |

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