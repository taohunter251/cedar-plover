from __future__ import annotations

from sceneforge.schema.config import BudgetConfig
from sceneforge.schema.rates import RateTable
from sceneforge.schema.responses_api import TokenUsage
from sceneforge.schema.spent import Spent


class BudgetExhausted(RuntimeError):
    pass


class PromptBudget:
    def __init__(self, config: BudgetConfig, rates: RateTable):
        self._config = config
        self._rates = rates
        self.spent = Spent()

    def can_call(self, count: int = 1) -> bool:
        return (
            self.spent.unknown_usage_calls == 0
            and self.spent.calls + count <= self._config.max_calls_per_prompt
            and self.spent.credits < self._config.max_credits_per_prompt
        )

    def begin_call(self, model: str, bound: TokenUsage) -> None:
        if not self.can_call():
            raise BudgetExhausted(self.spent.model_dump_json())
        worst = self._rates.call_credits(model, bound)
        if self.spent.credits + worst > self._config.max_credits_per_prompt:
            raise BudgetExhausted(f"{self.spent.model_dump_json()} cannot reserve {worst:.0f} credits")
        self.spent.calls += 1

    def finish_call(self, model: str, usage: TokenUsage | None) -> None:
        if usage is None:
            self.spent.unknown_usage_calls += 1
        else:
            self.spent.credits += self._rates.call_credits(model, usage)
