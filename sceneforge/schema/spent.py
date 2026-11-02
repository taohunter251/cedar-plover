from __future__ import annotations

from pydantic import BaseModel


class Spent(BaseModel):
    calls: int = 0
    credits: float = 0.0
    unknown_usage_calls: int = 0
