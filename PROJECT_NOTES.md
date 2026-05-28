# Folio - Engineering Notes

A reference document for the design decisions, the things you can claim during a demo, and the next-step improvements to articulate when the interviewer pushes.

---

## 1. What this project is

Single-user, local-first medical-record companion. Inputs: PDFs, photos of paper reports, photos of body parts (skin, eye, wound), voice notes, free text. Output: a unified structured JSON schema persisted in MongoDB, plus a chat companion that answers questions about your record using retrieval-grounded reasoning.

Core problem: **transforming unstructured medical inputs into structured, longitudinal data, then making the structure queryable through conversation.**

---

## 2. Stack

```
Frontend           Backend                Storage / Cache       LLM Providers
─────────────      ──────────────         ───────────────       ─────────────
Vite + React       FastAPI                MongoDB (Motor)       Anthropic
Tailwind CSS       Python 3.11 async      Redis (response       (Claude Sonnet 4.6,
React Query        SSE streaming           + embedding cache)    Claude Haiku 4.5)
Recharts           Pydantic v2            GridFS (attachments)
React Router       OpenTel-style spans                          OpenAI
                                                                (GPT-4.1, Whisper,
                                                                text-embedding-3-small)
                                                                Gemini
                                                                (Gemini 2.5 Flash/Pro)
```

Deployed free-forever via Vercel (frontend) + Render (backend) + Atlas M0 (Mongo) + Upstash (Redis).

---

## 3. What has been built - feature-by-feature

### 3.1 Multimodal ingest pipeline

| Input | Path | Models used |
|---|---|---|
| Free text | `POST /api/ingest/text` | Claude Haiku → JSON via streaming |
| PDF | `POST /api/ingest/pdf` | `pdfplumber` for native text → Claude Haiku JSON; if image-only PDF, rasterize 10 pages → Gemini Flash vision OCR → Claude Haiku JSON |
| Photo | `POST /api/ingest/image` | Claude Sonnet **vision-clinical** prompt: returns the unified schema directly. Handles *both* body-part photos (fills `symptoms` with visible findings + `red_flags` for concerning features) and paper-report photos in one pass. |
| Voice | `POST /api/ingest/voice` | Whisper (`whisper-1`) for ASR → Claude Haiku JSON |

All four converge on the same `ExtractedReport` schema (`backend/app/schemas.py`) so persistence, embedding, and downstream suggestions are identical regardless of input modality.

**Code:** `backend/app/routers/ingest.py`, `backend/app/pipeline/{extraction,pdf_extract,pii}.py`, `backend/app/models/router.py`.

### 3.2 Multi-LLM consensus extraction (Arcsine-pattern)

`POST /api/consensus` runs three frontier LLMs in parallel (Claude Sonnet 4.6, GPT-4.1, Gemini 2.5 Pro) on the same input. For each field of the unified schema it then:

1. Embeds the canonical key per item using OpenAI `text-embedding-3-small`
2. Greedy-clusters items across model outputs by cosine similarity (threshold 0.78) so semantically equivalent values collide ("T2DM" ≈ "Type 2 diabetes mellitus")
3. Picks the cluster representative per cluster
4. Reports a per-field confidence = `unique_providers_in_cluster / models_succeeded`
5. Computes overall agreement = mean of per-field confidences

The UI surfaces this as a "Consensus run" panel: provider dots per field, color-coded confidence (green ≥99%, amber ≥66%, red below), inline mini-matrix in the chat thread when the consensus mode triggered the ingest.

**Code:** `backend/app/pipeline/consensus.py`, `backend/app/routers/consensus.py`.

**Why this matters:** Interview-relevant. Mirrors Arcsine's multi-LLM evaluation + alignment-verification stages directly. You can credibly say:
> "I ran three frontier models in parallel; instead of asking them to debate (which causes correlated failure when they all hallucinate the same way), I aligned their outputs with embedding similarity - that's a vector-based consensus check, not an LLM-based one."

### 3.3 RAG over patient records

Every persisted report is embedded via `text-embedding-3-small`; the embedding goes into a `report_embeddings` Mongo collection. On every chat turn we embed the latest user message, run brute-force cosine over all report embeddings, and inject the top-k passages (k=4, threshold 0.18) into the chat system prompt as cited evidence.

The chat UI renders **citation chips** under each Folio reply linking to the cited reports, with the similarity score on each chip. The system prompt explicitly tells the model to cite by report date, preventing fabricated values.

**Code:** `backend/app/rag/{embeddings,store}.py`, `backend/app/routers/chat.py`.

**Why brute-force cosine:** for <1000 reports the entire embedding table fits in memory, brute-force runs in <10ms, and the implementation has zero ops cost (no vector DB to maintain). Swappable for Atlas Vector Search or pgvector by changing one function - the abstraction stays.

### 3.4 Chat companion with patient-grounded system prompt

`POST /api/chat` (SSE-streamed). On every turn:

1. Builds a snapshot of the patient's current state (active diagnoses, current meds with doses, latest of each vital, last 15 labs with reference ranges and flags, recent report summaries, open red flags) from Mongo.
2. Runs RAG retrieval (above) on the latest user message.
3. Combines snapshot + retrieved passages into the system prompt (cache-controlled `ephemeral` so multi-turn conversations only pay for the user-message tokens after the first turn).
4. Streams Claude Sonnet's response token-by-token.
5. Falls back to GPT-4.1 if Anthropic fails.

System-prompt guardrails: never diagnose, never invent dosages, escalate hard red-flag symptoms ("call 911 now"), redirect off-topic questions, cite by report date when referencing history.

**Code:** `backend/app/routers/chat.py`, `frontend/src/pages/Chat.tsx`.

### 3.5 Cold-path suggestions engine

After every ingest, six suggestion generators run in parallel via `asyncio.gather` in a fire-and-forget background task:

| Generator | Source | LLM? |
|---|---|---|
| Trends | vitals_timeline + labs_timeline (deterministic Python) | No - LLM only writes the natural-language summary |
| Drug interactions | curated interaction table (RxNorm/openFDA-style) | **No** - explicitly avoids LLM hallucination of dosage/interaction risk |
| Follow-ups | guideline-based recheck calendar (deterministic) | No |
| Differentials | symptoms + active dx + labs → Claude Sonnet | Yes (cold path, quality over latency) |
| Lifestyle | active conditions → canned dietary patterns | No |
| Risk indicators | BP + LDL + HbA1c → simplified cardiometabolic + CKD heuristics | No - explicitly says "insufficient data" rather than inventing |

Each generator is wrapped in `_safe_run` so one failure doesn't take down the others.

**Code:** `backend/app/suggestions/`.

### 3.6 Hot-path / cold-path separation

The hot path is: receive input → PII scrub → cache check → LLM extraction → persist → embed. Single sequential bottleneck (the LLM call). Pre/post processing is gathered.

After persistence completes, an `asyncio.create_task` fires the suggestions engine (cold path) and returns control immediately. The user sees their extraction in <2s; the suggestions inbox updates ~5–10s later via React Query cache invalidation.

**Code:** `backend/app/routers/ingest.py::_pipeline` and `::_spawn_suggestions`.

### 3.7 Streaming SSE with tolerant partial-JSON parsing

The hot-path LLM streams JSON tokens. The frontend has a tolerant partial-JSON parser (`frontend/src/lib/partialJson.ts`) that walks the buffer, tracks brace/bracket depth and string state, then closes any open structures so it can render *complete-looking* JSON mid-stream. Result: the user sees fields populating section-by-section (diagnoses first, then meds, vitals, labs, symptoms, red flags) within ~700ms, even when full extraction takes 2–3s. **Perceived latency << actual latency.**

### 3.8 Vision-clinical analysis (not OCR)

Image ingest used to be OCR-only and was useless for clinical photos with no text. Replaced with a vision-clinical prompt to Claude Sonnet that:

- Returns the unified schema directly from the image
- Populates `symptoms` with visible observations (location, color, distribution, size, borders, signs of inflammation)
- Populates `red_flags` for concerning features
- Lists possible differentials in `raw_summary` using HEDGED language only ("findings consistent with…", "differential includes…") - never "this is X"
- Explicitly forbidden from filling `diagnoses` from a body-part photo unless the image *contains* a diagnosis label

Original image bytes are stored in GridFS (`backend/app/storage.py`) so the report-detail page can show a download button + inline preview instead of the garbled CID-glyph text that pdfplumber emits when fonts have no ToUnicode map.

### 3.9 Multi-model routing with explicit per-task justification

`backend/app/models/router.py` defines a `ModelChoice` per task with a one-line justification baked in as a comment. The Dev panel surfaces the routing table at runtime so anyone watching the demo can see the cost/quality/latency trade-off. Examples:

| Task | Primary | Fallback | Reason |
|---|---|---|---|
| Hot-path extraction | Claude Haiku 4.5 | Gemini 2.5 Flash | lowest TTFT among frontier models, prompt-cacheable |
| Vision OCR | Gemini 2.5 Flash | Claude Sonnet 4.6 | fastest multi-page document vision; fallback for handwriting |
| Voice | Whisper-1 | Gemini 2.5 Flash | best English ASR including medical vocab |
| Medical reasoning | Claude Sonnet 4.6 | GPT-4.1 | calibrated about uncertainty, says "insufficient data" |
| Vision-clinical | Claude Sonnet 4.6 | Gemini 2.5 Pro | strongest medical vision + careful hedging |

### 3.10 Latency observability

Per-stage latency is emitted as SSE `stage` events during ingest, then persisted on the report doc as `latency_ms = {pii_scrub_ms, llm_first_token_ms, llm_total_ms, persist_ms, total_ms, ...}`. The Dev panel aggregates p50/p95/p99 across the last 50 instrumented requests and renders a stacked bar visualization per request showing where time was spent.

Targets: **p50 <2s, p95 <3s** end-to-end on the hot path.

### 3.11 PII scrubbing before any model call

Regex-first scrubber catches SSN, email, phone, MRN, DOB. <5ms in-process, no provider exposure. Runs *before* both the LLM call AND the cache key computation (so identical scrubbed inputs hit the cache regardless of original PII).

**Code:** `backend/app/pipeline/pii.py`.

### 3.12 Caching at two layers

1. **Anthropic prompt caching** - the (large) extraction system prompt + few-shot examples are marked `cache_control: ephemeral` so identical-prompt calls within ~5min hit the cache and only the user message tokens are billed.
2. **Redis response cache** - key = `sha256(scrubbed_input + system_prompt_version + model_id)`, TTL 24h. Identical re-uploads return instantly with no API call.
3. **Embedding cache** - same Redis instance keyed on `sha256(text + embedding_model)`, TTL 30 days.

**Code:** `backend/app/cache.py`, `backend/app/rag/embeddings.py`.

### 3.13 Single-aggregation overview

The Overview endpoint uses one `$facet` aggregation in Mongo to fetch active diagnoses, active meds, latest of each vital type, top 3 unfdismissed suggestions, and recent red flags - all in one round trip. Indexes on `(uploaded_at desc)`, `(recorded_at desc, type)`, `(severity, dismissed, created_at desc)`, etc. defined at startup.

### 3.14 Free-forever deployment

`render.yaml` blueprints the backend service. `frontend/vercel.json` configures the SPA. `DEPLOY.md` walks step-by-step: Atlas M0 → Upstash → Render → Vercel → CORS lock. Update flow: `git push` → both auto-deploy. Anthropic / OpenAI / Gemini keys are pay-per-use only, so the recurring cost is genuinely $0.

---

## 4. Novel methods (interview talking points)

### 4.1 Embedding-based field-level consensus
Instead of asking models to debate (Arcsine's "self-reflection" stage, which is the standard approach but suffers from correlated failure when models share training data), I align outputs with **vector similarity**. Claim: cheaper, faster, immune to "all models confidently agree on the same hallucination" because the alignment is computed externally from the model. The trade-off: embeddings can mark two wrong-but-equivalent values as "agreeing", which is why the system also keeps a per-cluster `votes` count and would flag low-confidence fields for human review in production.

### 4.2 Streaming + tolerant partial JSON
Emitting structured JSON token-by-token and rendering progressively as it arrives is unusual - most apps wait for the full response. The custom partial-JSON parser closes open structures speculatively, letting React render complete-looking nested objects mid-stream. **Perceived latency is what users experience.** First diagnosis on screen in ~700ms even when full extraction takes 2.5s.

### 4.3 Hot path vs cold path explicit separation
The user-facing latency budget contains *only* what the user is waiting on. Suggestions, embeddings (already in `gather`), risk scores, drug interactions all run after the response is closed. The architecture is honest about which work is on the critical path and which isn't - explicit in the code, not implicit.

### 4.4 Vision-clinical extraction unified with text extraction
Both code paths converge on the same `ExtractedReport` schema. The vision model is asked to populate `symptoms` (observations) and `red_flags` (concerning findings) instead of `diagnoses`, with hedged-language `raw_summary` for differentials. This means the same downstream pipeline (persist, embed, suggest, RAG) handles all input modalities without branching logic.

### 4.5 Deterministic computation where LLMs hallucinate
Drug interactions, follow-up calendars, risk scores, trend detection are pure Python. The LLM is only used to phrase them when needed. Specifically: the drug-interaction lookup is a curated table, not a model call. Dosage and interaction-severity hallucinations are catastrophic in clinical contexts; structurally avoiding them is a system-design choice, not a prompt-engineering one.

### 4.6 PII scrub before cache key + before model call
A subtle one - by scrubbing PII *before* computing the cache key, two re-uploads of the same content with different PII still hit cache. A naive implementation would scrub after caching and lose the dedup benefit.

### 4.7 Original-bytes preservation
Persisting the original PDF/image to GridFS *before* the LLM runs means the user can always download the source even when extraction fails. Most extraction systems lose the source after the first transformation.

---

## 5. Bottlenecks (be ready to be asked about these)

### 5.1 LLM call is the only sequential critical-path step
Both pre- and post-processing are gathered. The LLM provider's network round-trip is the hard floor on latency. Mitigations: streaming for perceived latency, prompt caching for repeat-cost, response caching for repeat inputs, fast-model routing for the hot path.

### 5.2 Brute-force cosine retrieval
Loads all embeddings into memory each request. Fine to ~1000 reports (single-user assumption); beyond that, swap for `pgvector` or Atlas Vector Search. The retrieval interface is one function - no other code changes needed.

### 5.3 Single-user model
No auth, no RBAC, no multi-tenant. Intentionally out of scope for the demo. Real product would need HIPAA-compliant infra (BAAs, audit logs, encryption-at-rest claims, SOC2).

### 5.4 GridFS for attachments
Works, but in production I'd put binaries in S3 (or R2) with a presigned URL handed to the frontend. GridFS bloats Mongo's working set and competes with the operational data for cache.

### 5.5 Free-tier deploy cold start (~30s on Render)
First request after 15min idle wakes the container. Mitigations: a cron-job ping every 14min keeps it warm; or pay $7/mo for always-on. Documented in DEPLOY.md.

### 5.6 No concurrency limits or backpressure
Currently nothing throttles concurrent ingests. A burst could exhaust the LLM provider's per-minute rate limit. Real product would queue and add per-user concurrency caps.

### 5.7 Consensus mode is expensive
3× the API cost vs single-model. Justified for high-stakes documents but should be opt-in (which it is, via the toggle). Production-ready version would auto-route to consensus only when single-model confidence is below a threshold (a confidence score from the model, or a quick second-opinion from a cheaper model that triggers a full-ensemble run).

### 5.8 RAG retrieval threshold is a magic number
`min_score=0.18` was set by eyeball. Real product needs a calibration set + offline eval to tune.

---

## 6. Improvements I'd make next

### 6.1 Confidence-driven routing
Today the user picks Standard or High-confidence. Better: run Standard, then have a small classifier (or a cheap LLM call) score the output's quality (e.g., "is this output internally consistent?"). If low → escalate to consensus. If high → done. Same UX, lower cost, better tail behavior.

### 6.2 Vector store proper
Move from brute-force cosine-in-memory to pgvector or Atlas Vector Search. Trivial code change (the retrieval API is one function); buys you HNSW indexing, persistence beyond reboot, and scaling beyond memory.

### 6.3 Reflection round (optional)
Currently when models disagree on a field, the system flags low confidence. Could add an optional second pass: feed the disagreed field + each model's answer back to a strong model and ask which is correct given the source. Costs 1 extra LLM call per disagreed field; gains accuracy on contentious values. Skipped today because of correlated-failure risk on simple "they all agree" cases.

### 6.4 Active learning from dismissals
Right now suggestions can be dismissed. The dismissed_suggestions log is unused. Real product: feature-extract dismissed-vs-acted suggestions and retrain a small ranker that orders the suggestion inbox per-user. Closes the human-in-the-loop feedback loop.

### 6.5 PDF.js for inline preview
The current `<object data="…pdf">` embedding works but quality varies by browser. Switch to PDF.js so we control rendering, can highlight extracted spans, and can show specific pages.

### 6.6 Fine-tune extraction on user corrections
The Report Detail page shows the structured extraction. Add an "edit / correct" affordance (already in the original spec, not yet built). Persist corrections; fine-tune a small open-weights model (e.g., Qwen 2.5 7B) on (input, correct extraction) pairs for personalized precision over time.

### 6.7 Observability beyond per-stage timing
Add OpenTelemetry traces with a `request_id` propagated through the full pipeline (frontend → backend → mongo/redis/llm). Today the latency events live on the report doc; in production I'd ship them to Honeycomb / Tempo / Datadog so I can debug a production incident without re-running the request.

### 6.8 Differential privacy for embedding storage
Embeddings of PHI text can leak information. Current code stores raw embeddings in Mongo. Production: encrypt at rest, restrict access via role, optionally use a noised variant for similarity search to add a privacy budget.

### 6.9 Synthetic eval set + regression CI
Build a fixed set of (input, expected extraction) pairs across the input modalities. Run on every PR. Fail the build if extraction precision drops. The seed dataset is a starting point but isn't a frozen eval.

### 6.10 Real EHR connectivity
FHIR R4 endpoints would let the system pull from a real chart instead of relying on the user to upload everything. Out of scope for a demo but the natural next step toward a real product.

---

## 7. Engineering trade-offs taken

| Decision | Alternative | Why I chose this |
|---|---|---|
| Brute-force cosine in Mongo | pgvector / Atlas Vector | Single-user → corpus stays small. Zero ops cost. Swap is one function. |
| Multi-LLM consensus opt-in | always-on | 3× cost; only worth it for high-stakes docs. User toggles. |
| SSE over WebSockets | WebSockets | One-way streaming server→client is exactly what we need. SSE auto-reconnects and works through more proxies. |
| Mongo over Postgres | Postgres + pgvector | Faster iteration on schema (medical schemas evolve). The `$facet` aggregation is genuinely cleaner than the equivalent SQL CTEs for the overview. |
| PDF text first, vision fallback | always vision | Native PDF text is deterministic, free, and finishes in <300ms. Vision is the fallback for image-only PDFs. |
| Vision-clinical replaces OCR for images | OCR + structured extraction in two steps | The vision model can do both in one pass; saves a hop and handles body-part photos correctly. |
| Drug interactions in curated DB | LLM | Hallucinated interaction warnings are dangerous. Curated table is a structural fix, not a prompt-engineering bandaid. |
| Hot/cold path explicit | unified pipeline | Suggestions take 5–10s; hot path budget is 2s. Cleanly separable. |

---

## 8. Direct mapping to Arcsine's pipeline

| Arcsine stage | Folio equivalent | Code |
|---|---|---|
| Multi-LLM generation | `consensus_extract()` runs Claude/GPT/Gemini in `asyncio.gather` | `pipeline/consensus.py` |
| Self-reflection / debate | **Not implemented**; replaced with embedding alignment (next bullet). Defensible: avoids correlated-failure consensus. | - |
| Embedding alignment | `cosine` clustering over `text-embedding-3-small` of canonical field keys, threshold 0.78 | `pipeline/consensus.py::FIELD_KEY` + `rag/embeddings.py::cosine` |
| Output evaluation | per-field confidence = unique_providers / models_succeeded; overall = mean of per-field | `pipeline/consensus.py::_overall_agreement` |
| Best output selection | per cluster, prefer Anthropic → OpenAI → Gemini representative; sort field by confidence desc | same |
| Edge handling (human review) | UI surfaces low-confidence fields with red color; production hook would route below threshold to a review queue | `frontend/src/pages/Ingest.tsx::ConsensusPanel` |

You can credibly say in the interview:

> "I built the same shape of pipeline they describe. The decision I made differently was using embedding-based alignment instead of an LLM-based reflection round. Reflection rounds are appealing but they create correlated failure when the models share training data - embedding alignment is computed external to the models and is significantly cheaper. I'd add reflection back as an optional escalation only on fields where embedding alignment shows low agreement."

---

## 9. Privacy posture (also interview-relevant)

Folio practices privacy at four layers:

1. **Data** - regex PII scrubber strips SSN, MRN, email, phone, DOB before the LLM call. Cache keys are computed on the scrubbed text.
2. **Model** - providers used (Anthropic, OpenAI, Gemini API tier) don't train on API inputs by default; we don't fine-tune on patient data.
3. **Infra** - cors origin allow-list locks browser access to the deployed frontend; `.env` keys are gitignored; HTTPS everywhere on the deployed URL.
4. **Governance** - disclaimer banner is permanent; "not medical advice" framing is in the system prompt and the UI; suggestions are dismissable and audit-logged.

For HIPAA: would need BAAs with each provider, encryption at rest claims for Mongo + Redis, audit logs for every read/write, RBAC for multi-user. Out of scope for a portfolio demo; explicitly called out as future work.

---

## 10. The 60-second pitch

> "Folio is a single-user medical record that ingests PDFs, photos, voice, and free text and produces a unified structured schema you can query in conversation. The hard parts are: streaming structured JSON so the user sees fields populating field-by-field instead of waiting; routing to different models per task with explicit justification (Whisper for voice, Gemini Flash for vision OCR, Claude Sonnet for medical reasoning); a multi-LLM consensus mode for high-stakes ingests that aligns three model outputs via embedding similarity instead of LLM debate; RAG retrieval over the user's own report history so the chat companion cites real data instead of fabricating; and explicit hot-path / cold-path separation so suggestions, drug-interaction checks, and risk scores run after the user already has their answer. Drug interactions hit a curated table, not the LLM, because hallucinated dosages are dangerous. p50 end-to-end latency is under 2s on the hot path; consensus mode runs in 6–10s in the background."
