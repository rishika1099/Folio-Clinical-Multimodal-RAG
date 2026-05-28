from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
import uuid


InputType = Literal["pdf", "image", "voice", "text"]
DiagStatus = Literal["active", "resolved", "suspected"]
VitalType = Literal["bp", "hr", "temp", "spo2", "weight", "bmi", "glucose"]
LabFlag = Literal["normal", "high", "low", "critical"]
Severity = Literal["mild", "moderate", "severe"]
Urgency = Literal["routine", "soon", "urgent", "emergent"]
SuggestionSeverity = Literal["info", "watch", "action"]
SuggestionCategory = Literal[
    "trend", "interaction", "followup", "differential", "lifestyle", "risk"
]


class Diagnosis(BaseModel):
    condition: str = ""
    icd10: str = ""
    status: DiagStatus = "active"
    confidence: float = 0.5


class Medication(BaseModel):
    name: str = ""
    dose: str = ""
    frequency: str = ""
    started_at: str = ""
    purpose: str = ""


class Vital(BaseModel):
    type: VitalType
    value: str
    unit: str = ""
    recorded_at: str = ""


class Lab(BaseModel):
    test: str
    value: str
    unit: str = ""
    reference_range: str = ""
    flag: LabFlag = "normal"


class Symptom(BaseModel):
    description: str
    onset: str = ""
    severity: Severity = "mild"


class RedFlag(BaseModel):
    finding: str
    reason: str
    urgency: Urgency = "routine"


class ExtractedReport(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    uploaded_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    input_type: InputType
    diagnoses: list[Diagnosis] = []
    medications: list[Medication] = []
    vitals: list[Vital] = []
    labs: list[Lab] = []
    symptoms: list[Symptom] = []
    red_flags: list[RedFlag] = []
    raw_summary: str = ""

    # Demo metadata (not part of the core schema, but useful for the dev panel)
    source_text: Optional[str] = None
    model_used: Optional[str] = None
    latency_ms: Optional[dict] = None

    # Original-file pointer (PDF / image). Stored in GridFS.
    attachment_id: Optional[str] = None
    attachment_mime: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_size: Optional[int] = None


class Suggestion(BaseModel):
    suggestion_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    category: SuggestionCategory
    severity: SuggestionSeverity = "info"
    title: str
    body: str
    evidence: list[str] = []
    report_id: Optional[str] = None
    dismissed: bool = False


class TextInputRequest(BaseModel):
    text: str
    note: str = ""


class User(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    display_name: str = ""
    password_hash: str
    email: Optional[str] = ""        # optional, used only for password-reset
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class UserPublic(BaseModel):
    user_id: str
    username: str
    display_name: str = ""
