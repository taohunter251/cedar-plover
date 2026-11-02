from __future__ import annotations

from pydantic import BaseModel, Field

from sceneforge.schema.responses_api import TokenUsage


class ModelRate(BaseModel):
    input_credits_per_token: float = Field(ge=0.0)
    output_credits_per_token: float = Field(ge=0.0)
    long_input_credits_per_token: float = Field(ge=0.0)
    long_output_credits_per_token: float = Field(ge=0.0)


class RateTable(BaseModel):
    credits_per_prompt: int = Field(gt=0)
    calls_per_prompt: int = Field(gt=0)
    long_context_above_input_tokens: int = Field(gt=0)
    models: dict[str, ModelRate]

    def call_credits(self, model: str, usage: TokenUsage) -> float:
        rate = self.models[model]
        if usage.input_tokens > self.long_context_above_input_tokens:
            return (usage.input_tokens * rate.long_input_credits_per_token
                    + usage.output_tokens * rate.long_output_credits_per_token)
        return usage.input_tokens * rate.input_credits_per_token + usage.output_tokens * rate.output_credits_per_token
