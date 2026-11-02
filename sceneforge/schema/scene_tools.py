from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from sceneforge.schema.prompt_book import PLACEHOLDER
from sceneforge.schema.responses_api import FunctionTool


class SceneTool(str, Enum):
    WRITE_SCENE = "write_scene"
    EDIT_SCENE = "edit_scene"
    RESTORE_SCENE_REVISION = "restore_scene_revision"
    READ_SCENE = "read_scene"


class WriteSceneArgs(BaseModel):
    content: str


class TextReplacement(BaseModel):
    old_string: str = Field(alias="oldString")
    new_string: str = Field(alias="newString")


class EditSceneArgs(BaseModel):
    edits: list[TextReplacement] = Field(min_length=1)
    from_revision: str | None = Field(default=None, alias="fromRevision")


class RestoreRevisionArgs(BaseModel):
    revision_id: str = Field(alias="revisionId")


class ReadSceneArgs(BaseModel):
    start_line: int | None = Field(default=None, ge=1, alias="startLine")
    end_line: int | None = Field(default=None, ge=1, alias="endLine")


ARGS: dict[SceneTool, type[BaseModel]] = {
    SceneTool.WRITE_SCENE: WriteSceneArgs,
    SceneTool.EDIT_SCENE: EditSceneArgs,
    SceneTool.RESTORE_SCENE_REVISION: RestoreRevisionArgs,
    SceneTool.READ_SCENE: ReadSceneArgs,
}


class ToolSpecs(BaseModel):
    directory: str
    tools: dict[SceneTool, FunctionTool]
    snippets: str

    @classmethod
    def load(cls, directory: str, files: Mapping[str, str]) -> ToolSpecs:
        paths = {tool: f"{directory}/{tool.value}.json" for tool in SceneTool}
        missing = [path for path in [*paths.values(), f"{directory}/snippets.md"] if path not in files]
        if missing:
            raise ValueError(f"tool specs missing: {missing}")
        tools = {tool: FunctionTool.model_validate_json(files[path]) for tool, path in paths.items()}
        return cls(directory=directory, tools=tools, snippets=files[f"{directory}/snippets.md"].strip())

    @model_validator(mode="after")
    def _check(self) -> ToolSpecs:
        for tool, spec in self.tools.items():
            path = f"{self.directory}/{tool.value}.json"
            if spec.name != tool.value:
                raise ValueError(f"{path} names the tool {spec.name!r}")
            if _structure(spec.parameters) != _structure(ARGS[tool].model_json_schema(by_alias=True)):
                raise ValueError(f"{path} parameters differ from {ARGS[tool].__name__}")
            expected = {"snippets"} if tool is SceneTool.EDIT_SCENE else set()
            if set(PLACEHOLDER.findall(spec.description)) != expected:
                raise ValueError(f"{path} description must have the placeholders {sorted(expected)}")
        if set(PLACEHOLDER.findall(self.snippets)) != {"snippet_lines"}:
            raise ValueError(f"{self.directory}/snippets.md must have the placeholder snippet_lines")
        return self

    def spec(self, tool: SceneTool, snippet_lines: int) -> FunctionTool:
        note = self.snippets.replace("{{snippet_lines}}", str(snippet_lines)) if snippet_lines else ""
        description = self.tools[tool].description.replace("{{snippets}}", note).strip()
        return self.tools[tool].model_copy(update={"description": description})


def _structure(schema: dict[str, Any]) -> Any:
    definitions = schema.get("$defs", {})

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return strip(definitions[node["$ref"].rsplit("/", 1)[1]])
            return {key: strip(value) for key, value in node.items() if key not in ("title", "description", "$defs")}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return strip(schema)


class SceneToolResult(BaseModel):
    ok: bool
    revision: str | None
    restored_from: str | None = None
    shown_lines: str | None = None
    error: str | None = None
