from __future__ import annotations

from pydantic import BaseModel

from sceneforge.schema.messages import FunctionCall
from sceneforge.schema.responses_api import TokenUsage


class LlmReply(BaseModel):
    text: str
    function_calls: list[FunctionCall] = []
    usage: TokenUsage | None
