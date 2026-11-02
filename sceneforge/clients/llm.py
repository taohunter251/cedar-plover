from __future__ import annotations

from typing import TYPE_CHECKING

from openai import APIError, APIStatusError
from pydantic import ValidationError

from sceneforge.schema.llm_reply import LlmReply
from sceneforge.schema.messages import FunctionCall
from sceneforge.schema.responses_api import ResponsesRequest, TokenUsage

if TYPE_CHECKING:
    from witness_client import AsyncWitnessClient

MAX_BODY_BYTES = 8 * 1024 * 1024
SESSION_ID_ON_API = "requires subscription"
TRANSIENT_STATUSES = {408, 409, 429}
TRANSIENT_CODES = {"server_error", "server_is_overloaded", "rate_limit_exceeded"}


class ProviderFailed(RuntimeError):
    def __init__(self, message: str, code: str | None, usage: TokenUsage | None):
        super().__init__(message)
        self.code = code
        self.usage = usage


class RequestRejected(ValueError):
    pass


def transient(error: BaseException) -> bool:
    if isinstance(error, APIStatusError):
        return error.status_code in TRANSIENT_STATUSES or error.status_code >= 500
    if isinstance(error, APIError | ProviderFailed):
        return error.code in TRANSIENT_CODES
    return False


def failure_usage(error: BaseException) -> TokenUsage | None:
    if isinstance(error, ProviderFailed) and error.usage is not None:
        return error.usage
    if isinstance(error, RequestRejected) or transient(error):
        return TokenUsage(input_tokens=0, output_tokens=0)
    return None


class Llm:
    def __init__(self, witness: AsyncWitnessClient):
        self._witness = witness

    async def call(self, request: ResponsesRequest, session_id: str | None = None, request_id: int = 0) -> LlmReply:
        size = len(request.model_dump_json().encode())
        if size > MAX_BODY_BYTES:
            raise RequestRejected(f"request body of {size} B exceeds the witness limit of {MAX_BODY_BYTES} B")
        arguments = request.model_dump(mode="json")
        try:
            try:
                result = await self._witness.responses.create(request_id=request_id, session_id=session_id,
                                                              **arguments)
            except ValueError as error:
                if SESSION_ID_ON_API not in str(error):
                    raise
                result = await self._witness.responses.create(request_id=request_id, **arguments)
        except ValueError as error:
            raise RequestRejected(str(error)) from error
        try:
            usage = TokenUsage.model_validate(result.usage, from_attributes=True)
        except ValidationError:
            usage = None
        if result.status != "completed":
            raise ProviderFailed(f"response {result.status}: {result.error or result.incomplete_details}",
                                 result.error.code if result.error else None, usage)
        calls = [FunctionCall.model_validate(item, from_attributes=True)
                 for item in result.output if item.type == "function_call"]
        return LlmReply(text=result.output_text, function_calls=calls, usage=usage)
