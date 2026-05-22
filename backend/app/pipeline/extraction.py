"""
Hot-path extraction. Streams structured JSON tokens from the chosen model.
Frontend uses a tolerant partial-JSON parser to render fields progressively.
"""
import json
from typing import AsyncIterator

from ..models.router import (
    ROUTE_EXTRACT_FALLBACK,
    ROUTE_EXTRACT_PRIMARY,
    stream_json,
)
from ..schemas import ExtractedReport

SYSTEM_PROMPT = """You are a clinical information extractor. Convert the user's medical text (lab report, discharge summary, symptom note, prescription, etc.) into a single JSON object that conforms to the schema below.

Output rules:
- Output a SINGLE JSON object and nothing else. No prose, no code fences.
- Use empty arrays for sections with no information. Do not invent data.
- For diagnoses: status must be one of "active", "resolved", "suspected"; confidence is 0..1.
- For labs.flag: one of "normal", "high", "low", "critical".
- For symptoms.severity: one of "mild", "moderate", "severe".
- For red_flags.urgency: one of "routine", "soon", "urgent", "emergent".
- For vitals.type: one of "bp", "hr", "temp", "spo2", "weight", "bmi", "glucose".
- raw_summary: 1-2 plain-English sentences covering the gist.
- Order fields exactly: diagnoses, medications, vitals, labs, symptoms, red_flags, raw_summary. (This lets the UI render progressively as the stream arrives.)

Schema:
{
  "diagnoses": [{"condition": "", "icd10": "", "status": "active", "confidence": 0.0}],
  "medications": [{"name": "", "dose": "", "frequency": "", "started_at": "", "purpose": ""}],
  "vitals": [{"type": "bp", "value": "", "unit": "", "recorded_at": ""}],
  "labs": [{"test": "", "value": "", "unit": "", "reference_range": "", "flag": "normal"}],
  "symptoms": [{"description": "", "onset": "", "severity": "mild"}],
  "red_flags": [{"finding": "", "reason": "", "urgency": "routine"}],
  "raw_summary": ""
}
"""


async def stream_extraction(text: str) -> AsyncIterator[str]:
    """Yields chunks of the JSON response as they stream from the model."""
    user = f"Extract structured medical data from the following text:\n\n---\n{text}\n---"
    async for chunk in stream_json(SYSTEM_PROMPT, user, ROUTE_EXTRACT_PRIMARY, ROUTE_EXTRACT_FALLBACK):
        yield chunk


async def extract_full(text: str, input_type: str) -> ExtractedReport:
    """Non-streaming convenience wrapper used by tests / seed."""
    buf = ""
    async for chunk in stream_extraction(text):
        buf += chunk
    try:
        data = json.loads(buf)
    except Exception:
        # Tolerant parse: trim to outermost braces.
        s, e = buf.find("{"), buf.rfind("}")
        data = json.loads(buf[s : e + 1]) if s != -1 and e != -1 else {}
    return ExtractedReport(input_type=input_type, source_text=text, **data)
