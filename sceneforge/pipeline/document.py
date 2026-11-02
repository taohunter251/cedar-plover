from __future__ import annotations

from sceneforge.schema.document import DocumentHistory, EditKind, Revision, TextEdit


class DocumentError(ValueError):
    pass


class Document:
    def __init__(self, history: DocumentHistory):
        self.history = history
        self.text = ""
        for revision in history.revisions:
            for edit in revision.edits:
                self.text = _apply(self.text, edit)

    @property
    def name(self) -> str:
        return self.history.name

    @property
    def head(self) -> str | None:
        return self.history.revisions[-1].id if self.history.revisions else None

    def text_at(self, revision_id: str) -> str:
        index = self._index(revision_id)
        text = self.text
        for revision in reversed(self.history.revisions[index + 1:]):
            for edit in reversed(revision.edits):
                text = _apply(text, TextEdit(offset=edit.offset, old=edit.new, new=edit.old))
        return text

    def write(self, content: str, author: str) -> Revision:
        if not content.strip():
            raise DocumentError("content is empty")
        if content == self.text:
            raise DocumentError(f"content is identical to the current {self.name}")
        return self._append(EditKind.WRITE, [TextEdit.between(self.text, content)], author)

    def replace(self, replacements: list[tuple[str, str]], author: str, from_revision: str | None = None) -> Revision:
        if self.head is None:
            raise DocumentError(f"the {self.name} is empty; write it first")
        if not replacements:
            raise DocumentError("there is nothing to replace")
        start = self.text if from_revision is None else self.text_at(from_revision)
        text, edits = start, []
        for number, (old, new) in enumerate(replacements, start=1):
            try:
                edit = self._locate(text, old, new)
            except DocumentError as error:
                raise DocumentError(f"edit {number} of {len(replacements)}: {error}; no edit was applied") from None
            text = _apply(text, edit)
            edits.append(edit)
        if start == self.text:
            return self._append(EditKind.REPLACE, edits, author)
        return self._append(EditKind.REPLACE, [TextEdit.between(self.text, start), *edits], author,
                            restored_from=from_revision)

    def restore(self, revision_id: str, author: str) -> Revision:
        target = self.text_at(revision_id)
        if target == self.text:
            raise DocumentError(f"{revision_id} is identical to the current {self.name}")
        return self._append(EditKind.RESTORE, [TextEdit.between(self.text, target)], author,
                            restored_from=revision_id)

    def _locate(self, text: str, old: str, new: str) -> TextEdit:
        if not old:
            raise DocumentError("the text to replace is empty")
        if old == new:
            raise DocumentError("the replacement is identical to the text it replaces")
        starts, offset = [], text.find(old)
        while offset >= 0:
            starts.append(offset)
            offset = text.find(old, offset + 1)
        if not starts:
            raise DocumentError(f"the text to replace was not found in the {self.name}")
        if len(starts) > 1:
            lines = ", ".join(str(line) for line in sorted({line_of(text, offset) for offset in starts}))
            raise DocumentError(
                f"the text to replace occurs {len(starts)} times in the {self.name} (lines {lines}); "
                "include more surrounding lines so it occurs once"
            )
        return TextEdit(offset=starts[0], old=old, new=new)

    def _index(self, revision_id: str) -> int:
        for index, revision in enumerate(self.history.revisions):
            if revision.id == revision_id:
                return index
        known = ", ".join(revision.id for revision in self.history.revisions) or "none"
        raise DocumentError(f"unknown revision {revision_id!r}; known revisions: {known}")

    def _append(self, kind: EditKind, edits: list[TextEdit], author: str,
                restored_from: str | None = None) -> Revision:
        revision = Revision(id=f"r{len(self.history.revisions) + 1}", kind=kind, edits=edits, author=author,
                            restored_from=restored_from)
        for edit in edits:
            self.text = _apply(self.text, edit)
        self.history.revisions.append(revision)
        return revision


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _apply(text: str, edit: TextEdit) -> str:
    end = edit.offset + len(edit.old)
    if edit.offset > len(text) or text[edit.offset:end] != edit.old:
        raise DocumentError(f"the edit at offset {edit.offset} does not match the text")
    return text[:edit.offset] + edit.new + text[end:]
