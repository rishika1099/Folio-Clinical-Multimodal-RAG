# Folio — Your medical record, in one place

Local-first multimodal medical intelligence app. Ingests PDFs, photos of paper reports, voice notes, and free text; converts everything into a single structured JSON schema; surfaces longitudinal trends, drug interactions, follow-up reminders, differential considerations, lifestyle suggestions, and risk indicators over time.

> **Not medical advice.** Folio surfaces patterns. Decisions about your care belong with a licensed clinician.

---

## Quick start

```bash
git clone <this repo>
cd "Medical Chatbot"
cp .env.example .env       # then edit .env and add your API keys (see below)
docker compose up --build
docker compose exec backend python -m app.seed   # populate sample data
```

Open:
- App: http://localhost:5173
- API docs: http://localhost:8000/docs

The seed script writes ~14 sample reports across 10 months (varied input types, realistic progression of HTN → pre-diabetes → T2DM → hyperlipidemia and treatment response). The dashboard, timeline charts, and suggestions inbox all populate immediately so you can demo without using a single API call.

---

## Where to add API keys

Open `.env` (which you copied from `.env.example`) in the project root and paste your keys:

```env
ANTHROPIC_API_KEY=sk-ant-api03-…
OPENAI_API_KEY=sk-proj-…
GEMINI_API_KEY=AIza…
```

Where to get each key:

| Provider | Used for | Get a key |
|---|---|---|
| **Anthropic** | hot-path extraction (Claude Haiku 4.5) and medical reasoning (Claude Sonnet 4.6) | https://console.anthropic.com/settings/keys |
| **OpenAI** | voice transcription (Whisper), extraction fallback (GPT-4.1) | https://platform.openai.com/api-keys |
| **Gemini** | vision OCR for scanned PDFs and photos, summarization | https://aistudio.google.com/app/apikey |

**Minimum to run real ingest:** `ANTHROPIC_API_KEY`. The other two unlock voice and vision input but are optional. The seed script does not call any LLM, so the dashboard works fine with no keys at all.

After editing `.env`, restart the backend so it picks up the new values:

```bash
docker compose restart backend
```

---

## What's where

```
backend/
  app/
    main.py                  # FastAPI app
    config.py                # settings, model IDs
    db.py                    # Motor (async Mongo) + index setup
    cache.py                 # Redis (response cache)
    schemas.py               # Pydantic models for the unified report schema
    models/router.py         # multi-model routing + provider clients
    pipeline/
      pii.py                 # regex PII scrubber
      pdf_extract.py         # pdfplumber + vision fallback
      extraction.py          # streaming hot-path extraction
      persist.py             # parallel Mongo upserts
    suggestions/             # 6 cold-path generators
    routers/                 # /api/ingest, /api/overview, /api/suggestions, /api/dev
    seed.py                  # 14-report sample dataset
frontend/
  src/
    App.tsx
    components/              # Shell, Card, Severity
    pages/                   # Overview, Ingest, Timeline, Suggestions, ReportDetail, Dev
    lib/                     # api, sse, partialJson, format
docker-compose.yml
MODEL_ROUTING.md             # which model for which task and why
ARCHITECTURE.md              # hot path / cold path sequence diagrams
```

---

## Demo script

1. **Overview** — vital tiles with severity-tinted left bars, active diagnoses with confidence bars, current medications, top suggestions, red-flag panel.
2. **New report → text** — paste:
   > BP this morning 144/92, persistent morning headaches for 2 weeks. Currently on lisinopril 20mg.
   The Pipeline column ticks `pii_scrub → llm_first_token → llm_total → persist` in real ms. The right column renders fields **as they stream**: diagnoses first, then meds, vitals, labs, symptoms, red flags.
3. **New report → image / pdf / voice** — same UI, different pre-processing path; the dev panel shows the extra stage (`vision_ocr` / `pdf_extract` / `transcribe`).
4. **Insights** — six suggestion categories, filterable, dismissable. Drug interactions hit a curated table — explicitly *not* the LLM.
5. **Timeline** — Recharts series for BP / HbA1c / LDL with gradient fills, plus a vertical report log.
6. **Engine (dev panel)** — model routing table with per-task justification, p50/p95/p99 from the last 50 reports, per-stage stacked bars per request.

---

## Deployment

### Option A — Local only (recommended for the demo)
That's already what `docker compose up` gives you. Single user, single laptop, no cloud cost. This matches the project's local-first design.

### Option B — Public URL via tunnel (for sharing a live demo)
Keep the stack on your laptop and expose `localhost:5173` with one of:

```bash
# Cloudflare Tunnel (free, no signup needed for quick tunnels)
brew install cloudflared
cloudflared tunnel --url http://localhost:5173

# or ngrok (free tier)
brew install ngrok
ngrok http 5173
```

Both print a public URL. Treat the link as semi-private — it goes down when your laptop sleeps.

### Option C — Cloud deploy
Overkill for a single-user app, but if you want it permanently online:

- **Render** (easiest):
  - Backend: web service from this repo, root `backend/`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Add env vars from your `.env`.
  - Frontend: static site, root `frontend/`, build `npm install && npm run build`, publish `dist/`. Add `VITE_API_URL=https://your-backend.onrender.com`.
  - MongoDB: use MongoDB Atlas free tier; set `MONGO_URL` to the Atlas connection string.
  - Redis: Render's Redis add-on or Upstash free tier.

- **Fly.io**: `fly launch` in `backend/` and `frontend/` separately; provision Mongo + Redis as Fly machines or use external Atlas/Upstash.

- **Railway**: connect the repo, point at `backend/` and `frontend/` as separate services, attach Mongo + Redis plugins.

In all three cases the only code change is setting `VITE_API_URL` in the frontend build to point at the deployed backend URL. Everything else is identical to local.

### Option D — Run without Docker
If you don't want Docker:

```bash
brew install mongodb-community redis python@3.11 node poppler
brew services start mongodb-community
brew services start redis

# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MONGO_URL=mongodb://localhost:27017
export REDIS_URL=redis://localhost:6379/0
export ANTHROPIC_API_KEY=...
uvicorn app.main:app --reload &
python -m app.seed

# frontend (new terminal)
cd ../frontend
npm install
npm run dev
```

---

## Claims this app is built to support

- "I parallelised pre- and post-processing with `asyncio.gather` — the only true bottleneck is the LLM call itself." → see `routers/ingest.py::_pipeline` and `pipeline/persist.py`.
- "Streaming means the user sees diagnoses in under a second even when the full response takes 2.5s." → SSE in `routers/ingest.py`, partial-JSON parsing in `frontend/src/lib/partialJson.ts`.
- "I separated the hot path from the cold path." → suggestions fire-and-forget in `routers/ingest.py::_spawn_suggestions`.
- "I route to different models per task and document why." → `MODEL_ROUTING.md` and `models/router.py`.
- "There's a latency breakdown panel showing exactly where time is spent per request." → `/dev` route + `routers/dev.py`.
- "Prompt caching plus response caching cuts API spend on repeat inputs to near zero." → Anthropic prompt caching in `models/router.py::_stream_one`, Redis response cache in `cache.py`.
- "Drug interactions hit a real drug database, not the LLM." → curated table in `suggestions/interactions.py`.

---

## Latency targets

| Stage | Target |
|---|---|
| PII scrub | <100ms |
| PDF text extract (native) | <300ms |
| Mongo history fetch | <50ms |
| LLM first token | <800ms |
| LLM full | <2.5s |
| Mongo upserts | <100ms |
| **End-to-end hot path** | **p50 <2s, p95 <3s** |
| Cold suggestions (async) | <10s |

---

## Out of scope

Auth, multi-user, RBAC, HIPAA, BAAs, audit logs, FHIR/HL7, mobile native, certified clinical decision support. Folio is a portfolio/demo project intended to showcase the unstructured→structured pipeline and the systems thinking behind it.
