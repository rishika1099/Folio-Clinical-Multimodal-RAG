"""
Multi-model routing layer.

Each capability ("extract_text", "vision_ocr", "transcribe", "reason", "summarize")
maps to a primary model + fallback. The choice is justified in MODEL_ROUTING.md
at the repo root and mirrored as comments next to each route below.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from ..config import settings


@dataclass
class ModelChoice:
    provider: str  # "anthropic" | "openai" | "gemini"
    model: str
    reason: str


# --- Routing decisions (also documented in MODEL_ROUTING.md) -----------------

# Hot-path structured extraction.
# Why Claude Haiku 4.5: lowest TTFT among frontier-tier models, strong instruction
# following, reliable JSON output, and Anthropic prompt caching cuts repeat-call
# cost on the system prompt + few-shots. Fallback Gemini Flash for similar latency
# profile and competitive medical-text accuracy.
ROUTE_EXTRACT_PRIMARY = ModelChoice("anthropic", settings.claude_fast_model,
    "Lowest-latency frontier model with reliable JSON; prompt-cacheable system prompt.")
ROUTE_EXTRACT_FALLBACK = ModelChoice("gemini", settings.gemini_fast_model,
    "Comparable latency, separate provider so a single-vendor outage does not block extraction.")

# Vision OCR for scanned PDFs / phone photos.
# Why Gemini 2.5 Flash: best-in-class throughput on multi-page document images,
# native multimodal, cheaper than Claude/GPT vision at similar accuracy on
# clinical layouts. Fallback Claude Sonnet for ambiguous/handwritten cases.
ROUTE_VISION_PRIMARY = ModelChoice("gemini", settings.gemini_fast_model,
    "Fast multimodal OCR with strong document-layout understanding at low cost.")
ROUTE_VISION_FALLBACK = ModelChoice("anthropic", settings.claude_strong_model,
    "Higher accuracy on handwriting and ambiguous medical shorthand.")

# Voice transcription.
# Why Whisper: still the de-facto best speech-to-text for English medical
# vocabulary; latency is acceptable; reliable timestamps. Fallback Gemini.
ROUTE_TRANSCRIBE_PRIMARY = ModelChoice("openai", settings.openai_transcribe_model,
    "Best-in-class English ASR including medical terminology.")
ROUTE_TRANSCRIBE_FALLBACK = ModelChoice("gemini", settings.gemini_fast_model,
    "Native audio input, useful when OpenAI is unavailable.")

# Differential diagnosis reasoning (cold path, quality > latency).
# Why Claude Sonnet 4.6: strongest medical reasoning in our internal evals,
# careful with caveats and uncertainty. Fallback GPT-4.1 for diversity.
ROUTE_REASON_PRIMARY = ModelChoice("anthropic", settings.claude_strong_model,
    "Best medical reasoning quality; calibrated about uncertainty.")
ROUTE_REASON_FALLBACK = ModelChoice("openai", settings.openai_strong_model,
    "Comparable quality, different training, useful for ensembling perspectives.")

# Lightweight summarization (lifestyle, follow-up wording, drug interaction prose).
# Why Gemini Flash: cheapest fast model with adequate quality for prose summaries
# of deterministic computations. Fallback Claude Haiku.
ROUTE_SUMMARIZE_PRIMARY = ModelChoice("gemini", settings.gemini_fast_model,
    "Cheap, fast, adequate quality for short prose summaries.")
ROUTE_SUMMARIZE_FALLBACK = ModelChoice("anthropic", settings.claude_fast_model,
    "Reliable fallback when Gemini quota is exhausted.")


# --- Provider clients --------------------------------------------------------

_anthropic = None
_openai = None
_gemini_configured = False


def _anthropic_client():
    global _anthropic
    if _anthropic is None and settings.anthropic_api_key:
        from anthropic import AsyncAnthropic
        _anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic


def _openai_client():
    global _openai
    if _openai is None and settings.openai_api_key:
        from openai import AsyncOpenAI
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


def _gemini_client():
    global _gemini_configured
    if not settings.gemini_api_key:
        return None
    if not _gemini_configured:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        _gemini_configured = True
    import google.generativeai as genai
    return genai


# --- Generation primitives ---------------------------------------------------


async def stream_json(
    system: str,
    user: str,
    choice: ModelChoice = ROUTE_EXTRACT_PRIMARY,
    fallback: Optional[ModelChoice] = ROUTE_EXTRACT_FALLBACK,
    max_tokens: int = 2000,
    timeout_s: float | None = None,
) -> AsyncIterator[str]:
    """Stream raw text tokens from the chosen model. Falls back on failure."""
    timeout_s = timeout_s or settings.extraction_timeout_s
    try:
        async for chunk in _stream_one(system, user, choice, max_tokens, timeout_s):
            yield chunk
        return
    except Exception:
        if fallback is None:
            raise
    async for chunk in _stream_one(system, user, fallback, max_tokens, timeout_s):
        yield chunk


async def _stream_one(
    system: str, user: str, choice: ModelChoice, max_tokens: int, timeout_s: float
) -> AsyncIterator[str]:
    if choice.provider == "anthropic":
        client = _anthropic_client()
        if client is None:
            raise RuntimeError("Anthropic key missing")
        # Use prompt caching on the (large) system prompt to cut repeat costs.
        async with client.messages.stream(
            model=choice.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
        return

    if choice.provider == "openai":
        client = _openai_client()
        if client is None:
            raise RuntimeError("OpenAI key missing")
        resp = await client.chat.completions.create(
            model=choice.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
        return

    if choice.provider == "gemini":
        genai = _gemini_client()
        if genai is None:
            raise RuntimeError("Gemini key missing")
        model = genai.GenerativeModel(choice.model, system_instruction=system,
            generation_config={"response_mime_type": "application/json", "max_output_tokens": max_tokens})
        # google-generativeai exposes a sync iterator; wrap it.
        loop = asyncio.get_event_loop()
        def _gen():
            return model.generate_content(user, stream=True)
        stream = await loop.run_in_executor(None, _gen)
        for piece in stream:
            text = getattr(piece, "text", None)
            if text:
                yield text
        return

    raise RuntimeError(f"Unknown provider {choice.provider}")


async def complete_json(
    system: str,
    user: str,
    choice: ModelChoice,
    fallback: Optional[ModelChoice] = None,
    max_tokens: int = 1500,
    timeout_s: float = 20.0,
) -> dict:
    """Non-streaming JSON completion. Returns parsed dict."""
    text = ""
    async for chunk in stream_json(system, user, choice, fallback, max_tokens, timeout_s):
        text += chunk
    return _safe_json(text)


async def complete_text(
    system: str,
    user: str,
    choice: ModelChoice,
    fallback: Optional[ModelChoice] = None,
    max_tokens: int = 800,
) -> str:
    text = ""
    async for chunk in stream_json(system, user, choice, fallback, max_tokens, settings.suggestion_timeout_s):
        text += chunk
    return text.strip()


def _safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    # Find the outermost JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return {}


async def transcribe_audio(audio_bytes: bytes, mime: str = "audio/webm") -> str:
    """Voice transcription via Whisper (primary) with Gemini fallback."""
    client = _openai_client()
    if client is not None:
        try:
            import io
            buf = io.BytesIO(audio_bytes)
            buf.name = f"clip.{mime.split('/')[-1]}"
            resp = await client.audio.transcriptions.create(
                model=settings.openai_transcribe_model, file=buf
            )
            return resp.text
        except Exception:
            pass
    # Gemini fallback (sync API).
    genai = _gemini_client()
    if genai is None:
        raise RuntimeError("No transcription provider available")
    loop = asyncio.get_event_loop()
    def _do():
        model = genai.GenerativeModel(settings.gemini_fast_model)
        return model.generate_content([
            {"mime_type": mime, "data": audio_bytes},
            "Transcribe this audio verbatim. Output only the transcript.",
        ]).text
    return await loop.run_in_executor(None, _do)


async def vision_extract_text(images: list[bytes], mime: str = "image/png") -> str:
    """Vision OCR. Returns plain text concatenated across images."""
    genai = _gemini_client()
    if genai is not None:
        try:
            loop = asyncio.get_event_loop()
            def _do():
                model = genai.GenerativeModel(settings.gemini_fast_model)
                parts = [{"mime_type": mime, "data": img} for img in images]
                parts.append("Transcribe all text visible in these medical document images. Preserve structure (headings, tables, values, units, dates). Output plain text only.")
                return model.generate_content(parts).text
            return await loop.run_in_executor(None, _do)
        except Exception:
            pass
    # Claude vision fallback.
    client = _anthropic_client()
    if client is None:
        raise RuntimeError("No vision provider available")
    import base64
    content = []
    for img in images:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": mime,
            "data": base64.b64encode(img).decode(),
        }})
    content.append({"type": "text", "text": "Transcribe all text visible in these medical document images. Preserve structure. Output plain text only."})
    msg = await client.messages.create(
        model=settings.claude_strong_model, max_tokens=3000,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(b.text for b in msg.content if hasattr(b, "text"))


# --- Clinical vision observation -------------------------------------------
#
# Routes to Claude Sonnet for clinical-image analysis. Strong medical vision
# performance, careful with hedging language. We deliberately ask the model
# to DESCRIBE what's visible rather than diagnose, and to populate the same
# unified schema that text/PDF extraction uses, so the rest of the pipeline
# (persist, embed, suggest) is identical regardless of input type.
#
# The system prompt tells the model:
#   - photos of body parts → fill `symptoms` (visible findings) and
#     `red_flags` if concerning; list possible differentials in raw_summary
#   - photos of paper documents/labels → fill structured fields normally
#   - both can be true → populate both
# -----------------------------------------------------------------------------

CLINICAL_VISION_SYSTEM_TEMPLATE = """You are Folio, a careful clinical observer looking at a photograph that {name} just shared with you. Speak directly to {name} in the second person ("you", "your"). NEVER use third-person clinical phrases like "the patient", "the image displays", "the individual" — talk to {name}, not about them.

The image will be one of:
  (a) a photograph of a body part — skin lesion, eye, wound, nail, mouth, etc.
  (b) a photograph of a paper medical document, lab report, or prescription label
  (c) a screenshot of an electronic record
  (d) some combination

Produce a SINGLE JSON object conforming to this schema:

{{
  "diagnoses":   [{{"condition": "", "icd10": "", "status": "active|resolved|suspected", "confidence": 0.0}}],
  "medications": [{{"name": "", "dose": "", "frequency": "", "started_at": "", "purpose": ""}}],
  "vitals":      [{{"type": "bp|hr|temp|spo2|weight|bmi|glucose", "value": "", "unit": "", "recorded_at": ""}}],
  "labs":        [{{"test": "", "value": "", "unit": "", "reference_range": "", "flag": "normal|high|low|critical"}}],
  "symptoms":    [{{"description": "", "onset": "", "severity": "mild|moderate|severe"}}],
  "red_flags":   [{{"finding": "", "reason": "", "urgency": "routine|soon|urgent|emergent"}}],
  "raw_summary": ""
}}

Rules — CRITICAL:

- `raw_summary` is what {name} reads first. Structure it like this:
    1. ONE opening sentence that names the most likely consideration, with hedged language. Example: "This looks consistent with a severe bullous dermatosis — possibly toxic epidermal necrolysis or a severe drug reaction." Don't say "the image displays". Lead with the consideration.
    2. ONE or TWO sentences describing what you see ON them, in second person: "I can see extensive blistering across your perioral area and chin, with crusting on your forehead."
    3. ONE closing sentence with the recommended next step + urgency: "Given how extensive this is, please seek urgent medical evaluation today."
  Keep it tight — 3–4 sentences total. Never write "this is X" with certainty — always hedge.

- For body-part photos, populate `symptoms` with neutral OBSERVATIONS (location, distribution, color, texture, size, borders). Example:
    {{"description": "Widespread erythema and possible epidermal detachment across face, cheeks, forehead, periorbital areas. Affected areas moist and inflamed.", "onset": "", "severity": "severe"}}

- Set `red_flags` for visible findings that warrant clinical attention (ulceration, signs of infection, ocular involvement, asymmetric lesion concerning for malignancy, signs of TEN/SJS, anaphylaxis). Use urgency = "emergent" only for true emergencies; "urgent" for "today"; "soon" for "this week".

- Do NOT populate `diagnoses` from a body-part photo unless the image contains a diagnosis label or report text explicitly stating one. Visual observations belong in `symptoms`/`red_flags`; possible differentials live in `raw_summary` as hedged language.

- For document/label photos, populate structured fields (medications, labs, vitals) directly from the visible text.

- If you genuinely cannot tell what's in the image, return all empty arrays and a raw_summary that says so plainly: "I can't make this image out clearly — could you re-take it with more light?"

- Output JSON only. No prose outside the JSON. No code fences."""


def build_clinical_vision_system(name: str) -> str:
    """Format the vision system prompt for a specific user.
    Falls back to 'you' framing if name is empty."""
    safe_name = (name or "the user").strip() or "the user"
    return CLINICAL_VISION_SYSTEM_TEMPLATE.format(name=safe_name)


async def vision_clinical_extract(
    images: list[bytes],
    mime: str = "image/png",
    user_name: str = "",
) -> AsyncIterator[str]:
    """
    Stream clinical-vision analysis of one or more images.

    user_name is used to personalise the system prompt so the model
    addresses the user directly (e.g. "Your image shows…") instead of
    talking about them in the third person.

    Tries Claude Sonnet first (best medical-image quality). If that fails
    for any reason — bad model name, billing, transient 5xx — fall back to
    Gemini Flash (Flash is on the free tier; Pro's free-tier RPM is 0).
    """
    import base64

    system_prompt = build_clinical_vision_system(user_name)

    claude_err: Exception | None = None
    client = _anthropic_client()
    if client is not None:
        content: list[dict] = []
        for img in images:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": mime,
                "data": base64.b64encode(img).decode(),
            }})
        content.append({"type": "text", "text":
            "Analyse this image and return the structured JSON per the schema."})
        try:
            async with client.messages.stream(
                model=settings.claude_strong_model,
                max_tokens=2500,
                system=[{"type": "text", "text": system_prompt,
                          "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
            ) as stream:
                async for piece in stream.text_stream:
                    yield piece
            return
        except Exception as e:
            claude_err = e
            print(f"[vision_clinical] Claude failed, falling back to Gemini Flash: {e!r}")

    # Gemini fallback — use Flash, not Pro. Free tier covers Flash; Pro is
    # paid-only as of 2026 and would 429 here.
    genai = _gemini_client()
    if genai is None:
        if claude_err is not None:
            raise RuntimeError(f"Claude vision failed and no Gemini key configured: {claude_err}")
        raise RuntimeError("No vision provider available")
    loop = asyncio.get_event_loop()
    def _do():
        model = genai.GenerativeModel(
            settings.gemini_fast_model,
            system_instruction=system_prompt,
            generation_config={"response_mime_type": "application/json", "max_output_tokens": 2500},
        )
        parts: list[Any] = [{"mime_type": mime, "data": img} for img in images]
        parts.append("Analyse this image and return the structured JSON per the schema.")
        return model.generate_content(parts, stream=True)
    try:
        stream = await loop.run_in_executor(None, _do)
        for piece in stream:
            text = getattr(piece, "text", None)
            if text:
                yield text
    except Exception as gemini_err:
        if claude_err is not None:
            raise RuntimeError(
                f"Both vision providers failed.\n"
                f"  Claude: {claude_err}\n"
                f"  Gemini: {gemini_err}"
            )
        raise
