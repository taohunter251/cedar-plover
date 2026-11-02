from __future__ import annotations

from pydantic import BaseModel

from sceneforge.schema.messages import InputItem


class Session(BaseModel):
    instructions: str
    input: list[InputItem] = []
    session_id: str | None = None
