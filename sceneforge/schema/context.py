from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from sceneforge.schema.critic_report import CriticReport
from sceneforge.schema.document import DocumentHistory
from sceneforge.schema.render_result import RenderOutcome


class PipelineSnapshot(BaseModel):
    model_config = ConfigDict(ser_json_bytes="base64", val_json_bytes="base64")

    image: bytes
    scene: DocumentHistory
    renders: dict[str, RenderOutcome] = {}
    reviews: dict[str, CriticReport] = {}
