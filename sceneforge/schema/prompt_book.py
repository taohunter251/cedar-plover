from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel, Field, PrivateAttr, ValidationInfo, model_validator

FRAGMENT_JOIN = "\n"
SECTION_BREAK = "\n\n---\n\n"
PLACEHOLDER = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def _read_fragment(files: Mapping[str, str], name: str) -> str:
    if name not in files:
        raise ValueError(f"prompt file missing: {name}")
    return files[name].rstrip("\n") + "\n"


class Section(BaseModel):
    fragments: list[str] = Field(min_length=1)

    def render(self, files: Mapping[str, str]) -> str:
        return FRAGMENT_JOIN.join(_read_fragment(files, name) for name in self.fragments)


class Document(BaseModel):
    sections: list[Section] = Field(min_length=1)

    def render(self, files: Mapping[str, str]) -> str:
        return SECTION_BREAK.join(section.render(files) for section in self.sections)


Prompt = str | Document


class PromptBook(BaseModel):
    prompts: dict[str, Prompt]

    _texts: dict[str, str] = PrivateAttr()
    _path: str | None = PrivateAttr(default=None)

    @classmethod
    def load(cls, path: str, files: Mapping[str, str]) -> PromptBook:
        if path not in files:
            raise ValueError(f"prompt book missing: {path}")
        book = cls.model_validate_json(files[path], context={"files": files})
        book._path = path
        return book

    @property
    def path(self) -> str | None:
        return self._path

    def sources(self) -> list[str]:
        names: list[str] = []
        for prompt in self.prompts.values():
            parts = [prompt] if isinstance(prompt, str) else [n for s in prompt.sections for n in s.fragments]
            names.extend(name for name in parts if name not in names)
        return names

    @model_validator(mode="after")
    def _load_fragments(self, info: ValidationInfo) -> PromptBook:
        files = (info.context or {}).get("files")
        if files is None:
            raise ValueError("missing `files` validation context")
        self._texts = {
            name: _read_fragment(files, prompt) if isinstance(prompt, str) else prompt.render(files)
            for name, prompt in self.prompts.items()
        }
        return self

    def __getitem__(self, name: str) -> str:
        return self._texts[name]

    def __contains__(self, name: str) -> bool:
        return name in self._texts

    def placeholders(self, name: str) -> set[str]:
        return set(PLACEHOLDER.findall(self[name]))

    def fill(self, name: str, **values: str) -> str:
        expected = self.placeholders(name)
        if expected != set(values):
            raise ValueError(f"{name}: placeholders {sorted(expected)} but values for {sorted(values)}")
        return PLACEHOLDER.sub(lambda match: values[match.group(1)], self[name])
