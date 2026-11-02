from __future__ import annotations

from pydantic import BaseModel, ValidationError

from sceneforge.pipeline.document import Document, DocumentError, line_of
from sceneforge.schema.config import SceneToolsConfig
from sceneforge.schema.document import EditKind, Revision, TextEdit
from sceneforge.schema.messages import FunctionCall, FunctionCallOutput
from sceneforge.schema.responses_api import FunctionTool
from sceneforge.schema.scene_tools import (
    ARGS,
    EditSceneArgs,
    ReadSceneArgs,
    RestoreRevisionArgs,
    SceneTool,
    SceneToolResult,
    WriteSceneArgs,
)

EDIT_TOOLS = (SceneTool.WRITE_SCENE, SceneTool.EDIT_SCENE, SceneTool.RESTORE_SCENE_REVISION)


class SceneTools:
    def __init__(self, scene: Document, config: SceneToolsConfig):
        self._scene = scene
        self._config = config

    def specs(self, reading: bool) -> list[FunctionTool]:
        tools = self._available() if reading else list(EDIT_TOOLS)
        return [self._config.specs.spec(tool, self._config.snippet_lines) for tool in tools]

    @staticmethod
    def is_read(call: FunctionCall) -> bool:
        return call.name == SceneTool.READ_SCENE.value

    def run(self, call: FunctionCall, author: str) -> FunctionCallOutput:
        result, lines = self._result(call, author)
        output = result.model_dump_json(exclude_unset=True) + (f"\n{lines}" if lines else "")
        return FunctionCallOutput(call_id=call.call_id, output=output)

    def _available(self) -> list[SceneTool]:
        return [*EDIT_TOOLS, *([SceneTool.READ_SCENE] if self._config.max_read_replies else [])]

    def _result(self, call: FunctionCall, author: str) -> tuple[SceneToolResult, str]:
        available = self._available()
        tool = next((tool for tool in available if tool.value == call.name), None)
        if tool is None:
            names = ", ".join(tool.value for tool in available)
            return self._failure(f"unknown tool {call.name!r}; available tools: {names}"), ""
        try:
            args = ARGS[tool].model_validate_json(call.arguments)
            if isinstance(args, ReadSceneArgs):
                return self._read(args)
            return self._edited(self._apply(args, author))
        except ValidationError as error:
            return self._failure("invalid arguments: " + "; ".join(
                f"{'.'.join(map(str, detail['loc'])) or 'arguments'}: {detail['msg']}" for detail in error.errors()
            )), ""
        except DocumentError as error:
            return self._failure(str(error)), ""

    def _apply(self, args: BaseModel, author: str) -> Revision:
        match args:
            case WriteSceneArgs():
                return self._scene.write(args.content, author)
            case EditSceneArgs():
                return self._scene.replace([(edit.old_string, edit.new_string) for edit in args.edits], author,
                                           from_revision=args.from_revision)
            case RestoreRevisionArgs():
                return self._scene.restore(args.revision_id, author)
        raise TypeError(f"no scene edit for {type(args).__name__}")

    def _edited(self, revision: Revision) -> tuple[SceneToolResult, str]:
        result = SceneToolResult(ok=True, revision=revision.id)
        if revision.restored_from is not None:
            result.restored_from = revision.restored_from
        if revision.kind is not EditKind.REPLACE or not self._config.snippet_lines:
            return result, ""
        replacements = revision.edits[1:] if revision.restored_from is not None else revision.edits
        text, context = self._scene.text, self._config.snippet_lines
        windows = []
        for start, end in _regions(replacements):
            first, last = line_of(text, start), line_of(text, max(start, end - 1))
            windows.append((first - context, last + context))
        result.shown_lines, lines = self._numbered(windows)
        return result, lines

    def _read(self, args: ReadSceneArgs) -> tuple[SceneToolResult, str]:
        if self._scene.head is None:
            return self._failure(f"the {self._scene.name} is empty; write it first"), ""
        total = len(self._scene.text.splitlines())
        first, last = args.start_line or 1, min(args.end_line or total, total)
        if first > last:
            return self._failure(f"no lines {first}-{last}; the {self._scene.name} has {total} lines"), ""
        shown, lines = self._numbered([(first, last)])
        return SceneToolResult(ok=True, revision=self._scene.head, shown_lines=shown), lines

    def _numbered(self, windows: list[tuple[int, int]]) -> tuple[str, str]:
        lines = self._scene.text.splitlines()
        merged: list[tuple[int, int]] = []
        for first, last in sorted((max(1, first), min(len(lines), last)) for first, last in windows):
            if merged and first <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], last))
            else:
                merged.append((first, last))
        body = "\n...\n".join(
            "\n".join(f"{number}\t{lines[number - 1]}" for number in range(first, last + 1)) for first, last in merged
        )
        return ", ".join(f"{first}-{last}" for first, last in merged) + f" of {len(lines)}", body

    def _failure(self, error: str) -> SceneToolResult:
        return SceneToolResult(ok=False, revision=self._scene.head, error=error)


def _regions(edits: list[TextEdit]) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    for edit in edits:
        start, end, shift = edit.offset, edit.offset + len(edit.old), len(edit.new) - len(edit.old)
        kept = []
        for region_start, region_end in regions:
            if region_end < start:
                kept.append((region_start, region_end))
            elif region_start > end:
                kept.append((region_start + shift, region_end + shift))
            else:
                start, end = min(start, region_start), max(end, region_end)
        regions = [*kept, (start, end + shift)]
    return sorted(regions)
