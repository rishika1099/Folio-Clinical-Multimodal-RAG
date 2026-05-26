# Folio

A personal medical-record companion. Drop a PDF lab report, a phone photo of a paper visit summary, a voice memo about a symptom, or just type how you're feeling — Folio extracts structure, builds a longitudinal timeline, and answers questions about your own record in chat.

The way personal medical history works is broken. The actual data of your care lives in PDFs in your downloads folder, photos in your camera roll, and notes in your phone. Nothing talks to anything. Every new clinic re-asks the same questions. Folio is a portfolio project that takes that mess seriously: one schema, one timeline, one place to ask.

Multi-user — sign up with a username + password, and your record is partitioned from every other user's. Runs locally on Docker, deploys free-forever. Explicitly not a medical device.

---

## Running it

```bash
git clone https://github.com/rishika1099/Folio-Clinical-Multimodal-RAG
cd Folio-Clinical-Multimodal-RAG
cp .env.example .env        # drop your Anthropic key in
docker compose up --build
```

App: http://localhost:5173 · API: http://localhost:8000/docs.

The app starts empty. Add a report from chat (drop a file or paste a report) and the overview, timeline, and suggestions populate as you go. For a screencast or a demo without using your own data, `docker compose exec backend python -m app.seed` writes 14 synthetic reports across 10 months.

### Keys

| Env var | Required? | What for |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | hot-path extraction (Claude Haiku) and chat reasoning (Claude Sonnet) |
| `OPENAI_API_KEY`    | optional | voice transcription (Whisper), embeddings, extraction fallback |
| `GEMINI_API_KEY`    | optional | vision OCR for scanned PDFs |
| `JWT_SECRET`        | recommended | bytes used to sign session tokens. Generate a long random value for production. |
| `ALLOW_SIGNUP`      | optional | `true` (default) lets anyone register. Switch to `false` once your trusted users are in. |

See `DEPLOY.md` for the free-tier hosting walkthrough (Render + Vercel + Atlas + Upstash).

---

## What's interesting

A few specific things that I'd want to talk about in an interview, with the code locations.

### Streaming JSON, parsed mid-stream
The hot-path extraction model streams JSON tokens over SSE. The frontend walks the partial buffer, tracks brace and bracket depth, and closes any open structures so it can render complete-looking nested objects mid-stream. Diagnoses appear on screen in ~700ms while the full extraction is still being generated. — `frontend/src/lib/partialJson.ts`, `backend/app/routers/ingest.py`

### Multi-LLM consensus by vector alignment, not LLM debate
Flipping the composer to "High-conf" runs Claude Sonnet, GPT-4.1, and Gemini 2.5 Pro in parallel against the same input. For each field of the schema, I embed every model's output, cluster items by cosine similarity (threshold 0.78), and pick the cluster with the most distinct providers in it. Per-field confidence is `unique_providers / models_succeeded`. The alignment check is vector-based — cheaper than a reflection round and immune to the correlated-failure pattern where three models confidently agree on the same hallucination. — `backend/app/pipeline/consensus.py`

### RAG over your own record
Every report is embedded on ingest (text-embedding-3-small, cached in Redis). On every chat turn the user's message is embedded, top-k passages are pulled via brute-force cosine (~10ms for <1000 reports — swap for pgvector when that breaks), and the matched passages are injected into the system prompt as cited evidence. The UI renders citation chips under each reply that deep-link back to the source report. The model can't fabricate "your last A1C was X" if X isn't in retrieved context. — `backend/app/rag/`, `backend/app/routers/chat.py`

### Drug interactions don't go through the LLM
A curated interaction table does the lookup; the LLM only phrases the result. I'm not comfortable having a language model invent dosages or interaction severities. — `backend/app/suggestions/interactions.py`

### Hot path vs cold path
The user-facing latency budget contains only what's on the critical path: PII scrub, cache check, LLM extraction, persist. Suggestions, embeddings, risk scores, and the cold-path differential-diagnosis Claude call run *after* the response is closed via `asyncio.create_task`. First field on screen <1s, full extraction <2.5s, suggestions inbox fills 5–10s later. — `backend/app/routers/ingest.py::_pipeline`

### Vision-clinical, not OCR, for photos
Image ingest used to OCR text — useless for a clinical photo of a skin lesion or eye. Now Claude Sonnet's vision pass produces the unified schema directly: `symptoms` get visible observations (location, distribution, borders, signs of inflammation), `red_flags` flag concerning features, and the summary gives hedged differential considerations. Never "this is X" — always "consistent with X". — `backend/app/models/router.py::vision_clinical_extract`

For the full design tour — including bottlenecks, trade-offs, what I'd build next, and how this maps to a multi-LLM clinical-extraction pipeline — see `PROJECT_NOTES.md`.

---

## Stack

FastAPI (async) · Motor (async Mongo) · Redis · GridFS for original-file storage · React + Vite + Tailwind · Recharts · server-sent events for streaming.

Frontend, backend, Mongo, and Redis each run as their own container under `docker compose`. Production deploys to Render (web service) + Vercel (static) + Atlas (M0) + Upstash (Redis) — all on permanent free tiers.

---

## Not in scope

Multi-user, HIPAA, audit logs, BAAs, FHIR/HL7, EHR integration, certified clinical decision support, mobile native. Folio is a single engineer's medical record; turning it into something a clinic could install is a different project.

---

## Licence

Copyright © 2026 Rishika. All rights reserved. See [LICENSE](./LICENSE). Published for portfolio review only — not licensed for use, copying, redistribution, or as ML training data.
