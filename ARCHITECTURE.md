# Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vite + React + Tailwind + Recharts + RQ)         │
│  - Streaming UI (SSE) with tolerant partial-JSON parser     │
│  - Pages: Overview, Ingest, Timeline, Suggestions, Detail,  │
│    Dev panel                                                │
└──────────────┬──────────────────────────────────────────────┘
               │ POST + SSE
┌──────────────▼──────────────────────────────────────────────┐
│  FastAPI backend (Python 3.11, async)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  /api/ingest/{text|pdf|image|voice}  ── HOT PATH ──▶ │   │
│  │  /api/overview, /api/timeline, /api/reports/{id}    │   │
│  │  /api/suggestions, /api/dev/{routes,latency}        │   │
│  └──────────────────────────────────────────────────────┘   │
│        │                  │                  │              │
│        ▼                  ▼                  ▼              │
│   Anthropic           OpenAI             Gemini             │
│   (Claude)            (GPT/Whisper)      (vision/audio)     │
│        │                  │                  │              │
│        └──────────┬───────┴──────────┬──────┘               │
│                   ▼                  ▼                      │
│             MongoDB (Motor)    Redis (response cache)       │
└─────────────────────────────────────────────────────────────┘
```

## Hot path — text/pdf/image/voice ingest

The user is waiting. Goal: p50 <2s, p95 <3s.

```
Client                Backend                   LLM            Mongo / Redis
  │  POST /ingest/...  │
  │ ───────────────────▶                                            
  │                    │ (T0)
  │                    │  asyncio.gather(                           
  │                    │    pii.scrub(text),    -- regex, <5ms      
  │                    │    history_fetch,      -- last 3 reports   
  │                    │    pdf_extract OR      -- 100-300ms        
  │                    │    vision_ocr OR       -- 600-1500ms        
  │                    │    transcribe          -- 800-2000ms        
  │                    │  )                                          
  │ event: stage       │                                          
  │ ◀───────────────────                                            
  │                    │  Redis GET cache_key                       
  │                    │  ───────────────────────────────────────▶  
  │                    │  ◀───── miss                              
  │                    │  
  │                    │  client.messages.stream(...)               
  │                    │  ─────────────────────▶                    
  │                    │  ◀── token chunk ───── (TTFT ~500-800ms)   
  │ event: token       │                                          
  │ ◀───────────────────                                            
  │  (UI starts rendering 'diagnoses' as soon as that field closes) 
  │                    │  ◀── ... ──                                
  │                    │  ◀── final ──                              
  │                    │                                            
  │                    │  asyncio.gather(                           
  │                    │    persist_report(),   -- parallel upserts 
  │                    │    cache.set_json(),   -- write-through    
  │                    │  )                                          
  │ event: report      │                                          
  │ event: done        │
  │ ◀───────────────────                                            
  │                    │
  │                    │  asyncio.create_task(run_suggestions)  ───▶ COLD PATH
```

Key design choices:
- **Single sequential bottleneck.** Pre- and post-processing are gathered. The LLM call is the only critical-path step.
- **Streaming, not buffering.** SSE pushes raw token chunks; the frontend reconstructs the JSON as it arrives.
- **Partial-JSON parsing on the client** (`frontend/src/lib/partialJson.ts`) tolerates open strings, arrays, and braces — closes them speculatively so we can render section-by-section while the backend is still streaming.
- **Cache lookup before the LLM call.** Identical re-uploads of the same scrubbed text within 24h skip the API entirely.

## Cold path — suggestions

Runs after the SSE stream closes. The user already has their extraction.

```
backend                                                 mongo / providers
  │
  │ asyncio.create_task( suggestions.run_all(report_id) )
  │      │
  │      │ asyncio.gather(
  │      │    detect_trends,        -- pure Python on vitals_timeline / labs_timeline
  │      │    check_interactions,   -- curated drug-interaction table (NOT the LLM)
  │      │    generate_followups,   -- guideline calendar (deterministic)
  │      │    generate_lifestyle,   -- canned dietary patterns by condition
  │      │    compute_risk_scores,  -- pure Python (cardiometabolic, CKD)
  │      │    generate_differentials, -- Claude Sonnet (medical reasoning, slow OK)
  │      │ )
  │      │
  │      ▼
  │   suggestions collection ◀── insert_many
```

The differentials suggestion is the only one that calls an LLM. The other five are deterministic computation; the LLM is at most used to phrase a body — we never let it invent values.

## Mongo schema

| Collection | Indexes | Purpose |
|---|---|---|
| `reports` | `report_id` unique, `uploaded_at` desc | full extracted reports (canonical record) |
| `diagnoses_master` | `condition` text | dedup'd active diagnoses |
| `medications_master` | `name` text | dedup'd active meds |
| `vitals_timeline` | `(recorded_at desc, type)` | time series, fast type-filter queries |
| `labs_timeline` | `(recorded_at desc, test)` | time series for charts |
| `suggestions` | `(severity, dismissed, created_at desc)`, `report_id` | inbox |
| `dismissed_suggestions` | — | audit log |

The overview endpoint is **one** `$facet` aggregation, not 5 round-trips.

## Observability

- Per-stage latency emitted as SSE `stage` events during ingest.
- Stored on each report doc as `latency_ms = {pii_scrub_ms, llm_first_token_ms, llm_total_ms, persist_ms, total_ms}`.
- `/api/dev/latency` aggregates p50/p95/p99 across the last 50 requests.
- The dev panel renders all of the above in the UI.

## Failure handling

- LLM call: 8s timeout, automatic fallback to a cross-vendor model on exception (`models/router.py::stream_json`).
- Mongo: short serverSelectionTimeoutMS so a stalled DB never hangs an HTTP response.
- Suggestions: each generator is wrapped in `_safe_run`; one failing generator does not take down the others.
- Redis cache failures: silently no-op; cache is best-effort, never load-bearing.
