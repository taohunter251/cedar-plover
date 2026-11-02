from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RenderedGrid(BaseModel):
    model_config = ConfigDict(ser_json_bytes="base64", val_json_bytes="base64")

    status: Literal["rendered"] = "rendered"
    png: bytes


class CandidateRejected(BaseModel):
    status: Literal["rejected"] = "rejected"
    failures: list[str]


RenderOutcome = Annotated[RenderedGrid | CandidateRejected, Field(discriminator="status")]
