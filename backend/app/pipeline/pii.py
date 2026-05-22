"""
Lightweight PII scrubbing.

Regex-first pass catches the high-frequency PII (SSN, phone, email, MRN-like
numbers). For a real product you would chain a spaCy NER model behind this; for
the demo the regex pass alone runs in <5ms and is good enough.
"""
import re

# Order matters: more specific patterns first.
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\bMRN[:\s]*\d{5,12}\b", re.IGNORECASE), "[REDACTED_MRN]"),
    (re.compile(r"\bDOB[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE), "[REDACTED_DOB]"),
]


def scrub(text: str) -> str:
    if not text:
        return text
    out = text
    for pat, repl in PATTERNS:
        out = pat.sub(repl, out)
    return out
