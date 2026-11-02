"""TuttiGenerator/solid-mango (sceneforge/) followed by one Astra high refine of its result, measured on stored modules (+0.293 over Tutti, 41 official prompts).
If the refine fails, is cut short or does not render, Tutti's own module is returned unchanged."""

from __future__ import annotations

from loguru import logger
from witness_client import AsyncWitnessClient

from miner import images, pipeline, rewrite
from miner.rewrite import Calls, check, code_of, finish, image_part, refine_content
from sceneforge.pipeline.orchestrator import generate_prompt

FIRST_CALL = 100  # request ids start at FIRST_CALL * rewrite.CALL_IDS, above Tutti's
STEP, STEPS = 2, 3  # the refine text's step numbers, as tested


async def generate(image: bytes, seed: int, witness: AsyncWitnessClient) -> str | None:
    used: list = []
    base = await generate_prompt(image, seed, witness, used)
    if base is None:
        return None
    grid, _ = await check(base, witness, rewrite.VIEWS)
    if grid is None:
        return base
    calls = Calls(witness)
    calls.k, calls.credits, calls.calls = FIRST_CALL, float(used[0].credits), int(used[0].calls)
    photo = image_part(images.photo_data_url(image))
    try:
        text, incomplete = await calls.ask(refine_content(STEP, STEPS, photo, grid, base), "high", pipeline.ASTRA)
    except pipeline.ModelFailure as e:
        logger.warning("Astra refine call failed ({}), keeping Tutti's module", e)
        return base
    if incomplete:
        return base
    cand = code_of(text)
    new_grid, errors = await check(cand, witness, rewrite.VIEWS)
    if new_grid is None:
        logger.info("Astra refine rejected ({}), keeping Tutti's module", errors[:1])
        return base
    return await finish(cand, witness)
