from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from sceneforge.schema.messages import InputItem
from sceneforge.schema.session import Session


class ReasoningEffort(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class Reasoning(BaseModel):
    effort: ReasoningEffort


class FunctionTool(BaseModel):
    type: Literal["function"] = "function"
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool = False


class ResponsesRequest(BaseModel):
    tools: list[FunctionTool] = []
    model: str
    reasoning: Reasoning
    max_output_tokens: int
    instructions: str
    input: list[InputItem]

    @classmethod
    def from_session(cls, session: Session, model: str, reasoning: Reasoning, max_output_tokens: int,
                     tools: list[FunctionTool]) -> ResponsesRequest:
        return cls(tools=tools, model=model, reasoning=reasoning, max_output_tokens=max_output_tokens,
                   instructions=session.instructions, input=session.input)


class TokenUsage(BaseModel):
    model_config = ConfigDict(strict=True)

    input_tokens: int
    output_tokens: int
