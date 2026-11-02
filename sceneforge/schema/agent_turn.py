from __future__ import annotations

from pydantic import BaseModel, Field

from sceneforge.schema.llm_reply import LlmReply
from sceneforge.schema.messages import FunctionCall


class AgentTurn(BaseModel):
    replies: list[LlmReply] = Field(min_length=1)

    @property
    def text(self) -> str:
        return self.replies[-1].text

    @property
    def function_calls(self) -> list[FunctionCall]:
        return [call for reply in self.replies for call in reply.function_calls]
