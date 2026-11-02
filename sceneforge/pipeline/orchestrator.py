from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from openai import APIConnectionError
from witness_client import RenderUnavailable, WitnessError

from sceneforge.clients.llm import Llm
from sceneforge.clients.render import render_candidate
from sceneforge.pipeline.agent import Agent
from sceneforge.pipeline.assets import (CONFIG_PATH, PLACEHOLDER_PATH, PRICING_PATH, PROMPTS_DIR, load_config,
                                        rate_table)
from sceneforge.pipeline.budget import BudgetExhausted, PromptBudget
from sceneforge.pipeline.context import PipelineContext
from sceneforge.pipeline.critique import parse_duel, parse_penalties, parse_report
from sceneforge.pipeline.diagnostics import log
from sceneforge.pipeline.measure import measure
from sceneforge.pipeline.placeholder import placeholder_module
from sceneforge.pipeline.scene_tools import SceneTools
from sceneforge.schema.config import LoopConfig, MinerConfig, RetryConfig
from sceneforge.schema.critic_report import CriticReport
from sceneforge.schema.messages import InputImage, InputText
from sceneforge.schema.render_result import CandidateRejected, RenderedGrid

if TYPE_CHECKING:
    from witness_client import AsyncWitnessClient

INFRASTRUCTURE_FAILURES = (APIConnectionError, WitnessError, RenderUnavailable)
S1_VIEWS = (("slightly left of the front", 30.0, 0.0), ("slightly right of the front", 330.0, 0.0),
            ("the front, from slightly below", 0.0, 15.0), ("the front, from slightly above", 0.0, -30.0))
S1_DRAW_THRESHOLD = 0.7
FRONT_NAMES = {(30.0, 0.0): "front-left", (330.0, 0.0): "front-right", (0.0, 15.0): "front from below",
               (0.0, -30.0): "front from above"}


async def rank_grids(selector: Agent, image: bytes, grids: list[bytes], retry: RetryConfig,
                     tag: str) -> list[float] | None:
    labels = [chr(ord("A") + index) for index in range(len(grids))]
    content: list[InputText | InputImage] = [InputImage.from_png(image)]
    for label, grid in zip(labels, grids):
        content += [InputText(text=f"Candidate {label}:"), InputImage.from_png(grid)]
    content.append(InputText(text=selector.book.fill("SELECT", labels=", ".join(labels))))
    try:
        reply = await selector.ask(content, retry)
    except INFRASTRUCTURE_FAILURES:
        raise
    except Exception as error:
        log(tag, f"selector call failed: {type(error).__name__}: {error}")
        return None
    penalties = parse_penalties(reply.text, labels)
    return None if penalties is None else [penalties[label] for label in labels]


class Run:
    def __init__(self, config: MinerConfig, llm: Llm, witness: AsyncWitnessClient, image: bytes, tag: str,
                 budget: PromptBudget, generation: int, draft: int = 0):
        self.loop: LoopConfig = config.loop
        own = config.loop.draft_loops[draft] if draft < len(config.loop.draft_loops) else None
        self.max_iterations = own.max_iterations if own else config.loop.max_iterations
        self.score_threshold = own.score_threshold if own else config.loop.score_threshold
        self.generation = generation
        self.witness = witness
        grid = config.renderer.refine or config.renderer.query
        self.options = grid.to_options()
        self.grid_views = [(FRONT_NAMES[(theta, phi)], index, phi == 0.0)
                           for index, (theta, phi) in enumerate(zip(grid.thetas or [], grid.phis or []))
                           if (theta, phi) in FRONT_NAMES]
        self.grid_size, self.grid_gap = len(grid.thetas or []), grid.gap
        self.front_options = config.renderer.query.to_options() if config.renderer.refine is not None else None
        self.fronts: dict[str, bytes | None] = {}
        self.kept: str | None = None
        around = config.renderer.around
        self.around_options = around.to_options() if around is not None and (own is None or own.around) else None
        self.tag = tag
        self.budget = budget
        self.context = PipelineContext.start(image)
        image_hash = hashlib.sha256(image).hexdigest()[:16]
        request_base = generation * (config.loop.call_retry.max_retries + 1)
        coder = config.actors.coder
        self.coder = Agent("coder", coder, llm, budget, SceneTools(self.context.scene, coder.scene_tools),
                           session_id=f"{image_hash}-coder", tag=tag, request_base=request_base)
        self.critic = Agent("critic", config.actors.critic, llm, budget, session_id=f"{image_hash}-critic", tag=tag,
                            request_base=request_base)
        selector = config.actors.selector
        self.selector = (Agent("selector", selector, llm, budget, session_id=f"{image_hash}-selector", tag=tag,
                               request_base=request_base)
                         if selector else None)

    async def refine(self) -> None:
        if self.loop.rewrite:
            return await self.rewrite()
        image = InputImage.from_png(self.context.image)
        changed = await self.coder_turn([image, InputText(text=self.coder.book.fill("FIRST_TURN"))])
        for iteration in range(self.max_iterations):
            outcome = await self.render() if changed else None
            repairs = 0
            while (not isinstance(outcome, RenderedGrid) and repairs < self.loop.max_repair_turns
                   and self.budget.can_call()):
                changed = await self.coder_turn([InputText(text=self.repair(outcome))])
                outcome = await self.render() if changed else None
                repairs += 1
            if not isinstance(outcome, RenderedGrid):
                log(self.tag, f"iteration {iteration}: no rendered revision after the repairs, stopping")
                return
            last = iteration == self.max_iterations - 1
            if last and self.selector is not None:
                return
            head = self.context.scene.head
            twin = self.context.twin(head, self.context.reviews)
            if twin is not None:
                log(self.tag, f"iteration {iteration}: {head} has the code of {twin}; reusing its review")
                report = self.context.reviews[twin]
            else:
                if not self.budget.can_call():
                    return
                around = await self.render_around()
                review = await self.critic.ask([
                    image,
                    InputImage.from_png(outcome.png),
                    *([InputImage.from_png(around)] if around is not None else []),
                    InputText(text=self.critic.book.fill(
                        "REVIEW", code=self.context.scene.text,
                        around=self.critic.book.fill("AROUND") if around is not None else "")),
                ], self.loop.call_retry)
                report = parse_report(review.text)
                if report is None:
                    log(self.tag, f"iteration {iteration}: critic reply is not a report, stopping")
                    return
            self.context.reviews[head] = report
            log(self.tag, f"iteration {iteration}: {self.context.scene.head} scored {report.score:.2f}, "
                          f"{len(report.issues)} issues")
            if report.stop or report.score >= self.score_threshold or last or not self.budget.can_call(2):
                return
            changed = await self.coder_turn([InputImage.from_png(outcome.png),
                                             InputText(text=self.critic_repair(report))])

    async def rewrite(self) -> None:
        image = InputImage.from_png(self.context.image)
        changed = await self.coder_turn([image, InputText(text=self.coder.book.fill("FIRST_TURN"))])
        outcome = await self.rewrite_repairs(image, await self.render() if changed else None)
        if isinstance(outcome, RenderedGrid):
            self.kept = self.context.scene.head
        for iteration in range(self.max_iterations):
            if self.kept is None:
                log(self.tag, f"rewrite {iteration}: no rendered revision to rewrite, stopping")
                return
            if not self.budget.can_call():
                return
            kept, render = self.kept, self.context.renders[self.kept].png
            code = self.context.scene.text_at(kept)
            content, measurements = [image, InputImage.from_png(render)], ""
            measured = self.measure(render)
            if measured is not None:
                lines, overlay = measured
                content.append(InputImage.from_png(overlay))
                measurements = self.coder.book.fill("MEASUREMENTS", lines=lines)
            changed = await self.coder_turn([*content, InputText(text=self.coder.book.fill(
                "REWRITE", revision=kept, code=code, chars=str(len(code)), measurements=measurements))])
            if not changed:
                log(self.tag, f"rewrite {iteration}: the coder left {kept} unchanged, stopping")
                return
            outcome = await self.rewrite_repairs(image, await self.render())
            head = self.context.scene.head
            if not isinstance(outcome, RenderedGrid):
                log(self.tag, f"rewrite {iteration}: {head} rejected; back to {kept}")
                self.back_to(kept)
            elif await self.accepts(kept, head):
                log(self.tag, f"rewrite {iteration}: {head} rendered and kept")
                self.kept = head
            else:
                log(self.tag, f"rewrite {iteration}: {head} rendered, gate kept {kept}")
                self.back_to(kept)

    def measure(self, render: bytes) -> tuple[str, bytes] | None:
        if not self.loop.measurements or not self.grid_views:
            return None
        try:
            return measure(self.context.image, render, self.grid_views, self.grid_size, self.grid_gap)
        except Exception as error:
            log(self.tag, f"measurements failed: {type(error).__name__}: {error}")
            return None

    async def accepts(self, kept: str, head: str) -> bool:
        if not self.loop.gate or self.selector is None or not self.budget.can_call(2):
            return True
        grids = [await self.front(kept), await self.front(head)]
        if None in grids:
            return True
        totals = [0.0, 0.0]
        for order in ([0, 1], [1, 0]):
            penalties = await rank_grids(self.selector, self.context.image, [grids[index] for index in order],
                                         self.loop.call_retry, self.tag)
            if penalties is None:
                log(self.tag, f"gate: no penalties; keeping {head}")
                return True
            for index, penalty in zip(order, penalties):
                totals[index] += penalty
        log(self.tag, f"gate: {kept} {totals[0]:g}, {head} {totals[1]:g}")
        return totals[1] <= totals[0]

    async def front(self, revision: str) -> bytes | None:
        if self.front_options is None:
            outcome = self.context.renders.get(revision)
            return outcome.png if isinstance(outcome, RenderedGrid) else None
        if revision not in self.fronts:
            outcome = await render_candidate(self.witness, self.context.scene.text_at(revision), self.front_options)
            self.fronts[revision] = outcome.png if isinstance(outcome, RenderedGrid) else None
        return self.fronts[revision]

    async def rewrite_repairs(self, image: InputImage,
                              outcome: RenderedGrid | CandidateRejected | None) -> RenderedGrid | CandidateRejected | None:
        repairs = 0
        while (not isinstance(outcome, RenderedGrid) and repairs < self.loop.max_repair_turns
               and self.budget.can_call()):
            failures = (outcome.failures if outcome is not None
                        else ["NO_MODULE: the reply did not write the module with write_scene"])
            changed = await self.coder_turn([image, InputText(text=self.coder.book.fill(
                "REWRITE_REPAIR", revision=self.head(), code=self.context.scene.text or "(empty)",
                failures="\n".join(failures)))])
            outcome = await self.render() if changed else None
            repairs += 1
        return outcome

    def back_to(self, revision: str) -> None:
        if self.context.scene.text != self.context.scene.text_at(revision):
            self.context.scene.restore(revision, "gate")

    async def final_revision(self) -> str | None:
        if self.loop.rewrite:
            return self.kept
        fallback = self.context.best_revision()
        candidates = self.candidates()
        if self.selector is None or len(candidates) < 2 or not self.budget.can_call(2):
            return fallback
        totals = dict.fromkeys(candidates, 0.0)
        for order in (candidates, candidates[::-1]):
            penalties = await self.rank(order)
            if penalties is None:
                log(self.tag, "selector reply has no penalty for every candidate; keeping the best critic score")
                return fallback
            for revision, penalty in penalties.items():
                totals[revision] += penalty
        lowest = min(totals.values())
        winners = [revision for revision in candidates if totals[revision] == lowest]
        choice = fallback if fallback in winners else winners[-1]
        log(self.tag, "selector penalties: " + ", ".join(f"{r} {p:g}" for r, p in totals.items()) + f"; chose {choice}")
        return choice

    def candidates(self) -> list[str]:
        seen, rendered = set(), []
        for revision, outcome in self.context.renders.items():
            text = self.context.scene.text_at(revision)
            if isinstance(outcome, RenderedGrid) and text not in seen:
                seen.add(text)
                rendered.append(revision)
        return rendered[-4:]

    async def rank(self, order: list[str]) -> dict[str, float] | None:
        grids = [self.context.renders[revision].png for revision in order]
        penalties = await rank_grids(self.selector, self.context.image, grids, self.loop.call_retry, self.tag)
        return None if penalties is None else dict(zip(order, penalties))

    async def coder_turn(self, content: list[InputText | InputImage]) -> bool:
        scene = self.context.scene
        head, count = scene.head, len(scene.history.revisions)
        turn = await self.coder.ask(content, self.loop.call_retry)
        added = [revision.id for revision in scene.history.revisions[count:]]
        edits = [call for call in turn.function_calls if not SceneTools.is_read(call)]
        failed = len(edits) - len(added)
        log(self.tag, f"coder turn: {len(turn.replies)} replies, head {head} -> {scene.head}, "
                      f"new revisions {', '.join(added) or 'none'}, "
                      f"tool calls {', '.join(call.name for call in turn.function_calls) or 'none'} "
                      f"({failed} edits failed)")
        return bool(added)

    async def render(self) -> RenderedGrid | CandidateRejected:
        scene = self.context.scene
        twin = self.context.twin(scene.head, self.context.renders)
        if twin is not None:
            log(self.tag, f"{scene.head} has the code of {twin}; reusing its render")
            outcome = self.context.renders[twin]
        else:
            outcome = await render_candidate(self.witness, scene.text, self.options)
        self.context.renders[scene.head] = outcome
        return outcome

    async def render_around(self) -> bytes | None:
        if self.around_options is None:
            return None
        head = self.context.scene.head
        twin = self.context.twin(head, self.context.around)
        if twin is not None:
            self.context.around[head] = self.context.around[twin]
        elif head not in self.context.around:
            outcome = await render_candidate(self.witness, self.context.scene.text, self.around_options)
            self.context.around[head] = outcome.png if isinstance(outcome, RenderedGrid) else None
        return self.context.around[head]

    def repair(self, outcome: CandidateRejected | None) -> str:
        if outcome is None:
            return self.coder.book.fill("NO_EDIT_RETRY", revision=self.head())
        return self.coder.book.fill("VALIDATION_REPAIR", failures="\n".join(outcome.failures), revision=self.head())

    def critic_repair(self, report: CriticReport) -> str:
        reviews = self.context.reviews
        return self.coder.book.fill(
            "CRITIC_REPAIR",
            revision=self.head(),
            score=f"{report.score:.2f}",
            revisions="\n".join(f"- {revision}: {review.score:.2f}" for revision, review in reviews.items()),
            matching_aspects="\n".join(f"- {aspect}" for aspect in report.matching_aspects) or "- (none listed)",
            issues="\n".join(f"- [{issue.severity.value}] {issue.description}" for issue in report.issues),
        )

    def head(self) -> str:
        return self.context.scene.head or "none"


async def generate_prompt(image: bytes, seed: int, witness: AsyncWitnessClient, used: list | None = None) -> str | None:
    tag = hashlib.sha256(image).hexdigest()[:10]
    rates = rate_table(PRICING_PATH)
    config = load_config(CONFIG_PATH, PROMPTS_DIR, rates)
    budget = PromptBudget(config.budget, rates)
    if used is not None:
        used.append(budget.spent)
    llm = Llm(witness)
    drafts: list[tuple[Run, str]] = []
    for generation in range(config.loop.max_generations):
        if len(drafts) == config.loop.drafts:
            break
        if generation and not budget.can_call():
            log(tag, f"no budget left for generation {generation}")
            break
        run = Run(config, llm, witness, image, tag, budget, generation, draft=len(drafts))
        exhausted = False
        try:
            await run.refine()
        except INFRASTRUCTURE_FAILURES:
            raise
        except BudgetExhausted as error:
            exhausted = True
            log(tag, f"generation {generation}: budget exhausted: {error}")
        except Exception as error:
            log(tag, f"generation {generation}: stopped by {type(error).__name__}: {error}")
        best = await run.final_revision()
        if best is not None:
            drafts.append((run, best))
        else:
            log(tag, f"generation {generation}: no rendered revision")
        if exhausted:
            break
    if not drafts:
        return await fallback(image, witness, config, tag, budget)
    run, best = drafts[await pick_draft(drafts, config, llm, budget, image, tag)]
    review = run.context.reviews.get(best)
    log(tag, f"done: generation={run.generation} best={best} score={review.score if review else None}"
             f" calls={budget.spent.calls} credits={budget.spent.credits:.0f} result=kept")
    return run.context.scene.text_at(best)


async def pick_draft(drafts: list[tuple[Run, str]], config: MinerConfig, llm: Llm, budget: PromptBudget,
                     image: bytes, tag: str) -> int:
    if len(drafts) < 2 or config.actors.selector is None or not budget.can_call(2):
        return 0
    retry = config.loop.call_retry
    selector = Agent("selector", config.actors.selector, llm, budget,
                     session_id=f"{hashlib.sha256(image).hexdigest()[:16]}-drafts", tag=tag,
                     request_base=config.loop.max_generations * (retry.max_retries + 1))
    grids = [await run.front(best) or run.context.renders[best].png for run, best in drafts]
    indices = list(range(len(drafts)))
    totals = [0.0] * len(drafts)
    for order in (indices, indices[::-1]):
        penalties = await rank_grids(selector, image, [grids[index] for index in order], retry, tag)
        if penalties is None:
            log(tag, "draft selection failed; keeping the first draft")
            return 0
        for index, penalty in zip(order, penalties):
            totals[index] += penalty
    ranked = sorted(indices, key=lambda index: (totals[index], index))
    choice = ranked[0]
    log(tag, "draft penalties: " + ", ".join(f"g{run.generation} {total:g}" for (run, _), total in zip(drafts, totals))
             + f"; ranked first g{drafts[choice][0].generation}")
    if config.loop.final_duel and len(drafts) > 2 and budget.can_call(2 * len(S1_VIEWS)):
        first, second = ranked[0], ranked[1]
        diff = await duel(selector, image, [drafts[first], drafts[second]], config, retry, tag)
        if diff is not None and diff > S1_DRAW_THRESHOLD:
            choice = second
        log(tag, f"final duel g{drafts[first][0].generation} vs g{drafts[second][0].generation}: "
                 f"penalty difference {diff if diff is None else round(diff, 2)}; chose g{drafts[choice][0].generation}")
    return choice


async def duel(selector: Agent, image: bytes, pair: list[tuple[Run, str]], config: MinerConfig,
               retry: RetryConfig, tag: str) -> float | None:
    views: list[list[bytes]] = []
    for run, best in pair:
        code = run.context.scene.text_at(best)
        renders = []
        for _, theta, phi in S1_VIEWS:
            options = config.renderer.query.model_copy(update={"thetas": [theta], "phis": [phi]}).to_options()
            outcome = await render_candidate(run.witness, code, options)
            if not isinstance(outcome, RenderedGrid):
                log(tag, f"final duel: g{run.generation} did not render alone; skipping the duel")
                return None
            renders.append(outcome.png)
        views.append(renders)
    reference = InputImage.from_png(image)
    consistent: list[tuple[float, float]] = []
    for (angle, _, _), first, second in zip(S1_VIEWS, *views):
        answers = []
        for one, two in ((first, second), (second, first)):
            content = [InputText(text="Reference image (target object):"), reference,
                       InputText(text="3D model 1:"), InputImage.from_png(one),
                       InputText(text="3D model 2:"), InputImage.from_png(two),
                       InputText(text=selector.book.fill("DUEL", angle=angle))]
            try:
                reply = await selector.ask(content, retry)
            except INFRASTRUCTURE_FAILURES:
                raise
            except Exception as error:
                log(tag, f"final duel call failed: {type(error).__name__}: {error}")
                return None
            answers.append(parse_duel(reply.text))
        ab, ba = answers
        if ab is None or ba is None:
            continue
        diff_ab, diff_ba = ab[0] - ab[1], ba[1] - ba[0]
        if (diff_ab > 0 > diff_ba) or (diff_ab < 0 < diff_ba):
            continue
        consistent.append(((ab[0] + ba[1]) / 2, (ab[1] + ba[0]) / 2))
    if not consistent:
        return None
    return sum(first for first, _ in consistent) / len(consistent) - sum(second for _, second in consistent) / len(consistent)


async def fallback(image: bytes, witness: AsyncWitnessClient, config: MinerConfig, tag: str,
                      budget: PromptBudget) -> str | None:
    source = placeholder_module(image, PLACEHOLDER_PATH)
    outcome = await render_candidate(witness, source, config.renderer.query.to_options())
    rendered = isinstance(outcome, RenderedGrid)
    log(tag, f"done: calls={budget.spent.calls} credits={budget.spent.credits:.0f}"
             f" result={'placeholder' if rendered else 'none'}"
             + ("" if rendered else f" (placeholder rejected: {'; '.join(outcome.failures)})"))
    return source if rendered else None
