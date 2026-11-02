from __future__ import annotations

import base64
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ImageDetail(str, Enum):
    AUTO = "auto"
    LOW = "low"
    HIGH = "high"


class InputText(BaseModel):
    type: Literal["input_text"] = "input_text"
    text: str


class InputImage(BaseModel):
    type: Literal["input_image"] = "input_image"
    image_url: str
    detail: ImageDetail = ImageDetail.HIGH

    @classmethod
    def from_png(cls, png: bytes) -> InputImage:
        return cls(image_url="data:image/png;base64," + base64.b64encode(png).decode("ascii"))


InputContent = Annotated[InputText | InputImage, Field(discriminator="type")]


class UserMessage(BaseModel):
    type: Literal["message"] = "message"
    role: Literal["user"] = "user"
    content: list[InputContent]


class AssistantMessage(BaseModel):
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: str


class FunctionCall(BaseModel):
    type: Literal["function_call"] = "function_call"
    call_id: str
    name: str
    arguments: str


class FunctionCallOutput(BaseModel):
    type: Literal["function_call_output"] = "function_call_output"
    call_id: str
    output: str


Message = Annotated[UserMessage | AssistantMessage, Field(discriminator="role")]
InputItem = Annotated[Message | FunctionCall | FunctionCallOutput, Field(discriminator="type")]
