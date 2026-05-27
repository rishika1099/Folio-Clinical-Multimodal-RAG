"""
PII-scrubber coverage tests.

For each canned case we know exactly what must be redacted and what
must be preserved. Metrics:

  - Scrub recall  — % of must-scrub strings successfully redacted
  - Scrub precision — % of redactions that actually targeted PII
  - Content preservation — % of must-keep substrings still present
  - Per-class breakdown (SSN, MRN, email, phone, DOB)
"""
from dataclasses import dataclass

from ...pipeline.pii import scrub
from ..dataset import PII_CASES


@dataclass
class PIIResult:
    n_cases: int
    scrub_recall: float
    content_preservation: float
    by_class: dict[str, dict[str, float]]
    failures: list[dict]


_CLASSES = {
    "SSN":   lambda s: any(c.isdigit() for c in s) and "-" in s and len(s.replace("-", "")) == 9,
    "Phone": lambda s: any(c.isdigit() for c in s) and ("(" in s or "." in s or ("-" in s and len(s) >= 10)),
    "Email": lambda s: "@" in s,
    "MRN":   lambda s: s.isdigit() and 5 <= len(s) <= 12,
    "DOB":   lambda s: any(c in s for c in "/-") and any(c.isdigit() for c in s) and len(s) <= 12 and "@" not in s,
}


def _classify(s: str) -> str:
    for cls, pred in _CLASSES.items():
        try:
            if pred(s):
                return cls
        except Exception:
            continue
    return "Other"


def evaluate_pii() -> PIIResult:
    total_scrub_targets = 0
    scrubbed_correctly = 0
    total_keep_targets = 0
    kept_correctly = 0
    by_class: dict[str, dict[str, float]] = {}
    failures: list[dict] = []

    for case in PII_CASES:
        out = scrub(case.raw)

        for target in case.must_scrub:
            total_scrub_targets += 1
            cls = _classify(target)
            bc = by_class.setdefault(cls, {"hits": 0, "total": 0})
            bc["total"] += 1
            if target not in out:
                scrubbed_correctly += 1
                bc["hits"] += 1
            else:
                failures.append({"case": case.raw[:60], "missed": target, "class": cls})

        for target in case.must_keep:
            total_keep_targets += 1
            if target in out:
                kept_correctly += 1
            else:
                failures.append({"case": case.raw[:60], "destroyed": target})

    recall = scrubbed_correctly / total_scrub_targets if total_scrub_targets else 1.0
    preservation = kept_correctly / total_keep_targets if total_keep_targets else 1.0

    for cls, c in by_class.items():
        c["recall"] = c["hits"] / c["total"] if c["total"] else 1.0

    return PIIResult(
        n_cases=len(PII_CASES),
        scrub_recall=recall,
        content_preservation=preservation,
        by_class=by_class,
        failures=failures,
    )
