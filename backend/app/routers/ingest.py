"""
Ingest endpoints. Handles all four input types and produces a single SSE
stream that the frontend consumes. The stream emits:
  - event: stage     -> {"stage": "...", "ms": 123}      (latency markers)
  - event: token     -> "raw chunk of model output"      (streamed JSON)
  - event: report    -> full ExtractedReport JSON
  - event: error     -> {"message": "..."}
  - event: done      -> {"report_id": "..."}
"""
import asyncio
import json
import time
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..cache import cache_key, get_json, set_json
from ..pipeline.extraction import stream_extraction
from ..pipeline.pdf_extract import extract_pdf_text
from ..pipeline.persist import persist_report
from ..pipeline.pii import scrub
from ..models.router import (
    ROUTE_EXTRACT_PRIMARY,
    transcribe_audio,
    vision_clinical_extract,
    vision_extract_text,
)
from ..schemas import ExtractedReport
from ..storage import save_attachment
from ..suggestions.runner import run_all

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _sse(event: str, data) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def _pipeline(text: str, input_type: str, source_text: str | None,
                    extra_stages: list[tuple[str, float]] | None = None,
                    attachment: dict | None = None) -> AsyncIterator[bytes]:
    stages = list(extra_stages or [])
    t0 = time.perf_counter()

    # Pre-processing: PII scrub. Fast enough that we don't bother gathering.
    scrubbed = scrub(text)
    stages.append(("pii_scrub_ms", (time.perf_counter() - t0) * 1000))
    yield _sse("stage", {"stage": "pii_scrub", "ms": stages[-1][1]})

    # Cache lookup.
    key = cache_key(scrubbed, ROUTE_EXTRACT_PRIMARY.model, "v1")
    cached = await get_json(key)
    if cached:
        yield _sse("stage", {"stage": "cache_hit", "ms": 0})
        report = ExtractedReport(**cached, input_type=input_type, source_text=source_text)
        # Re-persist (so timeline rebuilds for repeat uploads).
        await persist_report(report)
        yield _sse("token", json.dumps(cached))
        yield _sse("report", report.model_dump())
        yield _sse("done", {"report_id": report.report_id})
        return

    # Stream extraction.
    t_llm = time.perf_counter()
    buf = ""
    first_token_ms = None
    try:
        async for chunk in stream_extraction(scrubbed):
            if first_token_ms is None:
                first_token_ms = (time.perf_counter() - t_llm) * 1000
                yield _sse("stage", {"stage": "llm_first_token", "ms": first_token_ms})
            buf += chunk
            yield _sse("token", chunk)
    except Exception as e:
        yield _sse("error", {"message": f"Extraction failed: {e}"})
        return

    llm_total_ms = (time.perf_counter() - t_llm) * 1000
    yield _sse("stage", {"stage": "llm_total", "ms": llm_total_ms})

    # Parse final JSON.
    try:
        s, e = buf.find("{"), buf.rfind("}")
        data = json.loads(buf[s : e + 1])
    except Exception:
        yield _sse("error", {"message": "Could not parse model JSON"})
        return

    report = ExtractedReport(input_type=input_type, source_text=source_text, **data,
                              model_used=ROUTE_EXTRACT_PRIMARY.model,
                              **(attachment or {}))

    # Post-processing in parallel.
    t_post = time.perf_counter()
    await asyncio.gather(
        persist_report(report),
        set_json(key, data),
    )
    post_ms = (time.perf_counter() - t_post) * 1000
    yield _sse("stage", {"stage": "persist", "ms": post_ms})

    total_ms = (time.perf_counter() - t0) * 1000
    report.latency_ms = {k: v for k, v in stages} | {
        "llm_first_token_ms": first_token_ms or 0,
        "llm_total_ms": llm_total_ms,
        "persist_ms": post_ms,
        "total_ms": total_ms,
    }
    yield _sse("report", report.model_dump())
    yield _sse("done", {"report_id": report.report_id})


def _spawn_suggestions(report_id: str):
    # Fire-and-forget background task. We don't await, so the response is
    # already closed by the time this runs. Caught at runner level.
    asyncio.create_task(run_all(report_id))


@router.post("/text")
async def ingest_text(payload: dict, background: BackgroundTasks):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")

    async def gen():
        report_id = None
        async for chunk in _pipeline(text, "text", text):
            if chunk.startswith(b"event: done"):
                # Extract report_id for the background task trigger.
                line = chunk.decode().split("\n", 2)[1]
                report_id = json.loads(line[len("data: "):])["report_id"]
            yield chunk
        if report_id:
            _spawn_suggestions(report_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/pdf")
async def ingest_pdf(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")
    filename = file.filename or "document.pdf"

    async def gen():
        t = time.perf_counter()
        text, method = await extract_pdf_text(content)
        ms = (time.perf_counter() - t) * 1000
        stages = [(f"pdf_extract_{method}_ms", ms)]
        yield _sse("stage", {"stage": f"pdf_extract_{method}", "ms": ms})
        if not text:
            yield _sse("error", {"message": "Could not extract any text from PDF"})
            return

        # Persist the original PDF bytes for download / preview.
        attachment = None
        try:
            file_id = await save_attachment(content, filename, "application/pdf")
            attachment = {"attachment_id": file_id, "attachment_mime": "application/pdf",
                          "attachment_filename": filename, "attachment_size": len(content)}
        except Exception as exc:
            print(f"[ingest_pdf] attachment save skipped: {exc}")

        report_id = None
        async for chunk in _pipeline(text, "pdf", text, extra_stages=stages, attachment=attachment):
            if chunk.startswith(b"event: done"):
                line = chunk.decode().split("\n", 2)[1]
                report_id = json.loads(line[len("data: "):])["report_id"]
            yield chunk
        if report_id:
            _spawn_suggestions(report_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/image")
async def ingest_image(file: UploadFile = File(...)):
    """
    Image ingest. Routes to a clinical-vision model that produces the full
    structured schema directly from the image. Handles BOTH cases in one
    pass:
      - photo of a body part / lesion / eye / wound → fills `symptoms` with
        visible observations + `red_flags` for concerning findings, plus a
        differential-considerations summary
      - photo of a paper report / label → fills medications/labs/vitals
        from the visible text
    """
    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")
    mime = file.content_type or "image/png"
    filename = file.filename or f"image.{mime.split('/')[-1]}"

    async def gen():
        t0 = time.perf_counter()

        # Persist the original bytes first so the user can always recover
        # the source image even if extraction errors.
        attachment = None
        try:
            file_id = await save_attachment(content, filename, mime)
            attachment = {"attachment_id": file_id, "attachment_mime": mime,
                          "attachment_filename": filename, "attachment_size": len(content)}
        except Exception as exc:
            print(f"[ingest_image] attachment save skipped: {exc}")

        # PII-scrub stage marker (no-op for binary image).
        yield _sse("stage", {"stage": "pii_scrub", "ms": 0})

        # Stream clinical-vision JSON directly from Claude Sonnet (or Gemini Pro fallback).
        t_llm = time.perf_counter()
        first_token_ms = None
        buf = ""
        try:
            async for piece in vision_clinical_extract([content], mime=mime):
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - t_llm) * 1000
                    yield _sse("stage", {"stage": "vision_first_token", "ms": first_token_ms})
                buf += piece
                yield _sse("token", piece)
        except Exception as e:
            yield _sse("error", {"message": f"Vision analysis failed: {e}"})
            return

        llm_total_ms = (time.perf_counter() - t_llm) * 1000
        yield _sse("stage", {"stage": "vision_total", "ms": llm_total_ms})

        # Parse final JSON.
        try:
            s, e = buf.find("{"), buf.rfind("}")
            data = json.loads(buf[s : e + 1])
        except Exception:
            yield _sse("error", {"message": "Could not parse vision-model JSON output"})
            return

        # Source-text best-effort: keep the raw_summary as a recoverable
        # textual representation. We DO NOT save the JSON blob as
        # source_text any more — the attachment is the source.
        source_text = data.get("raw_summary", "")

        report = ExtractedReport(
            input_type="image", source_text=source_text, **data,
            model_used="claude-sonnet (vision)",
            **(attachment or {}),
        )

        # Persist + cache + spawn suggestions.
        t_post = time.perf_counter()
        await asyncio.gather(
            persist_report(report),
            set_json(cache_key(buf, "vision-clinical", "v1"), data),
        )
        post_ms = (time.perf_counter() - t_post) * 1000
        yield _sse("stage", {"stage": "persist", "ms": post_ms})

        total_ms = (time.perf_counter() - t0) * 1000
        report.latency_ms = {
            "vision_first_token_ms": first_token_ms or 0,
            "vision_total_ms": llm_total_ms,
            "persist_ms": post_ms,
            "total_ms": total_ms,
        }
        yield _sse("report", report.model_dump())
        yield _sse("done", {"report_id": report.report_id})

        _spawn_suggestions(report.report_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/voice")
async def ingest_voice(file: UploadFile = File(...)):
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "empty audio")
    mime = file.content_type or "audio/webm"

    async def gen():
        t = time.perf_counter()
        try:
            text = await transcribe_audio(audio, mime=mime)
        except Exception as e:
            yield _sse("error", {"message": f"Transcription failed: {e}"})
            return
        ms = (time.perf_counter() - t) * 1000
        stages = [("transcribe_ms", ms)]
        yield _sse("stage", {"stage": "transcribe", "ms": ms})
        yield _sse("token", json.dumps({"transcript": text}))
        if not text:
            yield _sse("error", {"message": "Empty transcription"})
            return
        report_id = None
        async for chunk in _pipeline(text, "voice", text, extra_stages=stages):
            if chunk.startswith(b"event: done"):
                line = chunk.decode().split("\n", 2)[1]
                report_id = json.loads(line[len("data: "):])["report_id"]
            yield chunk
        if report_id:
            _spawn_suggestions(report_id)

    return StreamingResponse(gen(), media_type="text/event-stream")
