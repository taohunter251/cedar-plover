from __future__ import annotations

import os
from enum import Enum

from pydantic import BaseModel, Field


class TextEdit(BaseModel):
    offset: int = Field(ge=0)
    old: str
    new: str

    @classmethod
    def between(cls, before: str, after: str) -> TextEdit:
        prefix = len(os.path.commonprefix([before, after]))
        suffix = len(os.path.commonprefix([before[prefix:][::-1], after[prefix:][::-1]]))
        return cls(offset=prefix, old=before[prefix:len(before) - suffix], new=after[prefix:len(after) - suffix])


class EditKind(str, Enum):
    WRITE = "write"
    REPLACE = "replace"
    RESTORE = "restore"


class Revision(BaseModel):
    id: str = Field(description="revision id")
    kind: EditKind
    edits: list[TextEdit] = Field(min_length=1)
    author: str = Field(description="author agent")
    restored_from: str | None = None


class DocumentHistory(BaseModel):
    name: str
    revisions: list[Revision] = []
