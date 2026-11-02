from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from witness_client import RenderRejected, RenderUnavailable

from sceneforge.schema.render_result import CandidateRejected, RenderedGrid

if TYPE_CHECKING:
    from witness_client import AsyncWitnessClient, RenderOptions

MAX_SOURCE_BYTES = 1024 * 1024
RENDER_ATTEMPTS = 3
RETRY_DELAY_S = 2.0
MODULE_FAILURE_STATUS = 500
RENDER_FAILED = ("RENDER_FAILED: the renderer could not finish this module (it timed out or failed while drawing); "
                 "make the scene lighter")


async def render_candidate(witness: AsyncWitnessClient, code: str,
                           options: RenderOptions) -> RenderedGrid | CandidateRejected:
    if not code.strip():
        return CandidateRejected(failures=["EMPTY_REPLY: the reply contained no module"])
    size = len(code.encode("utf-8"))
    if size > MAX_SOURCE_BYTES:
        return CandidateRejected(failures=[f"FILE_SIZE_EXCEEDED: {size} bytes (limit {MAX_SOURCE_BYTES})"])
    for attempt in range(1, RENDER_ATTEMPTS):
        try:
            return await _render(witness, code, options)
        except RenderUnavailable:
            await asyncio.sleep(RETRY_DELAY_S * attempt)
    return await _render(witness, code, options)


async def _render(witness: AsyncWitnessClient, code: str, options: RenderOptions) -> RenderedGrid | CandidateRejected:
    try:
        return RenderedGrid(png=await witness.render(code, options))
    except RenderRejected as error:
        return CandidateRejected(failures=_failure_lines(error.details))
    except RenderUnavailable as error:
        if _status(error) != MODULE_FAILURE_STATUS:
            raise
        return CandidateRejected(failures=[RENDER_FAILED])


def _status(error: RenderUnavailable) -> int | None:
    return getattr(getattr(error.__cause__, "response", None), "status_code", None)


def _failure_lines(details: dict[str, object]) -> list[str]:
    lines = [f"{failure['rule']}: {failure['detail']}" for failure in details.get("failures") or []]
    if not lines:
        lines.append(f"{details['error']}")
    if details.get("truncated"):
        lines.append("(the renderer shortened this report)")
    if details.get("metrics"):
        lines.append(f"scene metrics: {json.dumps(details['metrics'], separators=(',', ':'))}")
    return lines
