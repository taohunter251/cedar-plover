from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CriticIssue(BaseModel):
    severity: Severity
    description: str


class CriticReport(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    stop: bool = False
    matching_aspects: list[str] = []
    issues: list[CriticIssue] = []
