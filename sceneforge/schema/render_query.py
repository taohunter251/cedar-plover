from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from witness_client import RenderOptions


class Lighting(str, Enum):
    FOLLOW = "follow"
    STUDIO = "studio"
    NEUTRAL = "neutral"


class RenderQuery(BaseModel):
    thetas: list[float] | None = None
    phis: list[float] | None = None
    img_size: int | None = None
    cam_radius: float | None = None
    cam_fov_deg: float | None = None
    gap: int | None = None
    bg_color: str | None = None
    lighting: Lighting | None = Field(default=None, description="preview lighting")

    def to_options(self) -> RenderOptions:
        return RenderOptions(**self.model_dump(mode="json", exclude_none=True))
