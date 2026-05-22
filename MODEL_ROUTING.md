# Model Routing

Every LLM-shaped task in this app picks a specific model. Choices below are encoded in `backend/app/models/router.py` and surfaced in the in-app dev panel at `/dev`. Cost is secondary; the optimization target is **latency on the hot path** and **medical accuracy on the cold path**.

Verify model IDs against your provider's current catalogue at deploy time — IDs drift.

| Task | Primary | Fallback | Justification |
|---|---|---|---|
| **PDF text extraction (native)** | `pdfplumber` (no LLM) | rasterize → vision route | Native text PDFs don't need a model; pdfplumber finishes in <300ms and is deterministic. |
| **OCR / vision (scanned PDFs, photos)** | Gemini 2.5 Flash | Claude Sonnet 4.6 | Gemini Flash is the fastest of the frontier vision models on multi-page document images and cheapest at scale; clinical layout fidelity is competitive with GPT-4o on our spot checks. Claude Sonnet falls back when the document includes handwriting or ambiguous medical shorthand where its accuracy edge matters more than throughput. |
| **Voice transcription** | Whisper (`whisper-1`) | Gemini 2.5 Flash | Whisper remains best-in-class for English including medical vocabulary; latency is acceptable for the cold-ish path of voice ingest. Gemini Flash takes audio natively and is the obvious fallback when OpenAI is unavailable. |
| **Hot-path structured extraction → JSON** | Claude Haiku 4.5 | Gemini 2.5 Flash | Lowest TTFT among frontier-tier models, strong instruction-following, reliable JSON output. Anthropic prompt caching on the (large) system prompt + few-shot examples cuts repeat-call cost to near zero. Gemini Flash is the cross-vendor fallback so a single-provider outage does not block extraction. **This is the model the user is waiting on.** |
| **Differential diagnosis reasoning (cold)** | Claude Sonnet 4.6 | GPT-4.1 | Strongest medical reasoning in our internal evals and notably calibrated about uncertainty (says "insufficient data" rather than confabulating). Quality > latency here because suggestions run in the background after the user already has their extraction. GPT-4.1 fallback for ensembling diversity. |
| **Trend detection / risk scores** | None (pure Python) | — | Deterministic, reproducible, no LLM hallucination surface. The LLM is *only* used to write the natural-language summary if the trend triggers. |
| **Drug interaction check** | Curated DB (RxNorm/openFDA-style table) | None | LLMs hallucinate dosages and false-positive interactions. The lookup MUST be a real database. We use a small curated table for the demo; production would use openFDA or DrugBank. |
| **Lifestyle / follow-up wording** | Gemini 2.5 Flash | Claude Haiku 4.5 | Cheapest fast model with adequate quality for short prose summaries of deterministic computations. Haiku is the fallback for vendor diversity. |
| **PII scrubbing** | Local regex (+ optional spaCy NER) | — | Runs in <5ms in-process; no network hop, no provider exposure of PHI. |

---

## Hard rule
For the hot-path extraction call, latency wins. For cold-path suggestions (where the user already has the extraction), quality wins.

## Why three providers, not one?
- **Single-vendor outage protection** — at least two of the three are reachable on any given day.
- **Best-tool-for-task** — vision favors Gemini, voice favors Whisper, medical reasoning favors Claude. Ensembling for free.
- **Real demo material** — the dev panel makes the routing visible and explains the trade-offs to anyone looking at the screen.

## How prompt caching is used
Anthropic prompt caching is enabled for the extraction system prompt (`backend/app/models/router.py::_stream_one`). The system prompt + few-shot exemplars are cache-controlled `ephemeral`, so identical-prompt calls within ~5 min hit the cache and only the user message tokens are billed.

## How response caching is used
After PII scrubbing, the request is hashed (`scrubbed_input + system_prompt_version + model_id`) and a Redis lookup is attempted before the LLM call. Identical re-uploads return instantly. TTL: 24h (`settings.cache_ttl_s`).
