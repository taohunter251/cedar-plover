from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from sceneforge.schema.prompt_book import PromptBook
from sceneforge.schema.rates import RateTable
from sceneforge.schema.render_query import RenderQuery
from sceneforge.schema.responses_api import ReasoningEffort
from sceneforge.schema.scene_tools import ToolSpecs

CODER_PROMPTS = {
    "SYSTEM": set(),
    "FIRST_TURN": set(),
    "VALIDATION_REPAIR": {"revision", "failures"},
    "CRITIC_REPAIR": {"revision", "score", "revisions", "matching_aspects", "issues"},
    "NO_EDIT_RETRY": {"revision"},
}
REWRITE_PROMPTS = {
    "REWRITE": {"revision", "code", "chars", "measurements"},
    "REWRITE_REPAIR": {"revision", "code", "failures"},
    "MEASUREMENTS": {"lines"},
}
CRITIC_PROMPTS = {"SYSTEM": set(), "REVIEW": {"code", "around"}, "AROUND": set()}
SELECTOR_PROMPTS = {"SYSTEM": set(), "SELECT": {"labels"}}
DUEL_PROMPTS = {"DUEL": {"angle"}}


class SceneToolsConfig(BaseModel):
    specs: ToolSpecs = Field(description="tool specs directory")
    snippet_lines: int = Field(ge=0, description="context lines around an edit; 0: none")
    max_read_replies: int = Field(ge=0, description="extra replies after a read; 0: no reads")

    @field_validator("specs", mode="before")
    @classmethod
    def _load_specs(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        files = (info.context or {}).get("files")
        if files is None:
            raise ValueError("missing `files` validation context")
        return ToolSpecs.load(value, files)


class AgentConfig(BaseModel):
    model: str
    reasoning_effort: ReasoningEffort
    max_output_tokens: int = Field(gt=0, description="output tokens per reply")
    keep_history: bool = Field(description="one session per prompt")
    prompts: PromptBook = Field(description="prompt book path")
    scene_tools: SceneToolsConfig | None = Field(default=None, description="None: no tools")
    send_session_id: bool = Field(default=False, description="send a session id")

    @field_validator("prompts", mode="before")
    @classmethod
    def _load_book(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value
        files = (info.context or {}).get("files")
        if files is None:
            raise ValueError("missing `files` validation context")
        return PromptBook.load(value, files)


class Actors(BaseModel):
    coder: AgentConfig
    critic: AgentConfig
    selector: AgentConfig | None = Field(default=None, description="None: keep the best critic score")


class RetryConfig(BaseModel):
    max_retries: int = Field(ge=0, description="repeats per call; 0: none")
    delay_ms: int = Field(ge=0, description="delay before a repeat, in ms")


class DraftLoop(BaseModel):
    max_iterations: int = Field(ge=1, description="refinement rounds")
    score_threshold: float = Field(ge=0.0, le=1.0)
    around: bool = Field(default=True, description="false: the critic never sees renderer.around")


class LoopConfig(BaseModel):
    max_generations: int = Field(ge=1, description="fresh starts per prompt")
    drafts: int = Field(default=1, ge=1, description="refined generations kept; the selector picks among them")
    draft_loops: list[DraftLoop] = Field(default=[], description="draft i refines as entry i says; [] or past "
                                                                 "the end: as this loop says")
    final_duel: bool = Field(default=False, description="the two best ranked drafts meet in a duel scored like the "
                                                         "judge's Stage 1: each front view alone, both orders")
    rewrite: bool = Field(default=False, description="each round rewrites the whole module in a fresh coder "
                                                     "context, without the critic; the newest render is kept")
    gate: bool = Field(default=False, description="a rewrite replaces the kept revision only when the selector "
                                                  "does not prefer the kept one over both orders in the front views")
    measurements: bool = Field(default=False, description="each rewrite also gets the photo's outline, proportions "
                                                          "and color measured against the render's front views")
    max_iterations: int = Field(ge=1, description="refinement rounds")
    max_repair_turns: int = Field(ge=0, description="repair turns per round")
    score_threshold: float = Field(ge=0.0, le=1.0)
    call_retry: RetryConfig


class BudgetConfig(BaseModel):
    max_calls_per_prompt: int = Field(ge=1, le=60, description="model calls per prompt")
    max_credits_per_prompt: float = Field(gt=0.0, le=5_000_000, description="credits per prompt")


class RendererConfig(BaseModel):
    query: RenderQuery = RenderQuery()
    refine: RenderQuery | None = None
    around: RenderQuery | None = None


class MinerConfig(BaseModel):
    actors: Actors
    loop: LoopConfig
    budget: BudgetConfig
    renderer: RendererConfig

    @classmethod
    def load(cls, config_json: str, files: Mapping[str, str], rates: RateTable) -> MinerConfig:
        return cls.model_validate_json(config_json, context={"files": files, "rates": rates})

    @model_validator(mode="after")
    def _check_actors(self, info: ValidationInfo) -> MinerConfig:
        rates = (info.context or {}).get("rates")
        if rates is None:
            raise ValueError("missing `rates` validation context")
        coder_prompts = {**CODER_PROMPTS, **(REWRITE_PROMPTS if self.loop.rewrite else {})}
        actors = [("coder", self.actors.coder, coder_prompts), ("critic", self.actors.critic, CRITIC_PROMPTS)]
        if self.actors.selector is not None:
            selector_prompts = {**SELECTOR_PROMPTS, **(DUEL_PROMPTS if self.loop.final_duel else {})}
            actors.append(("selector", self.actors.selector, selector_prompts))
        for name, actor, required in actors:
            if actor.model not in rates.models:
                raise ValueError(f"the rate table has no rate for the {name} model {actor.model!r}")
            missing = [prompt for prompt in required if prompt not in actor.prompts]
            if missing:
                raise ValueError(f"{name} prompt book {actor.prompts.path} lacks {missing}")
            for prompt, filled in required.items():
                found = actor.prompts.placeholders(prompt)
                if found != filled:
                    raise ValueError(f"{name} prompt {prompt} has placeholders {sorted(found)}, "
                                     f"expected {sorted(filled)}")
        if self.actors.coder.scene_tools is None:
            raise ValueError("the coder requires scene tools")
        if (self.loop.gate or self.loop.measurements) and not self.loop.rewrite:
            raise ValueError("the gate and the measurements need the rewrite loop")
        if self.loop.gate and self.actors.selector is None:
            raise ValueError("the gate needs a selector")
        if not self.actors.coder.keep_history and not self.loop.rewrite:
            raise ValueError("the coder keeps its history unless the loop rewrites")
        if self.actors.critic.scene_tools is not None:
            raise ValueError("the critic takes no scene tools")
        if self.actors.selector is not None and self.actors.selector.scene_tools is not None:
            raise ValueError("the selector takes no scene tools")
        return self
