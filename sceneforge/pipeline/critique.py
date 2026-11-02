from __future__ import annotations

import json
import re

from pydantic import ValidationError

from sceneforge.schema.critic_report import CriticReport

JSON_BLOCK = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.DOTALL)


def _json_candidates(text: str) -> list[str]:
    candidates = JSON_BLOCK.findall(text)
    if "{" in text:
        candidates.append(text[text.index("{") : text.rindex("}") + 1])
    return candidates


def parse_penalties(text: str, labels: list[str]) -> dict[str, float] | None:
    for candidate in _json_candidates(text):
        try:
            penalties = json.loads(candidate).get("penalties")
            values = {label: float(penalties[label]) for label in labels}
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        if all(0 <= value <= 10 for value in values.values()):
            return values
    return None


def parse_duel(text: str) -> tuple[float, float] | None:
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
            pair = (float(data["penalty_1"]), float(data["penalty_2"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        if all(0 <= value <= 10 for value in pair):
            return pair
    return None


def parse_report(text: str) -> CriticReport | None:
    for candidate in _json_candidates(text):
        try:
            return CriticReport.model_validate_json(candidate)
        except ValidationError:
            continue
    return None
