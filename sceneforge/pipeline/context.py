from __future__ import annotations

from collections.abc import Iterable

from sceneforge.pipeline.document import Document
from sceneforge.schema.context import PipelineSnapshot
from sceneforge.schema.critic_report import CriticReport
from sceneforge.schema.document import DocumentHistory
from sceneforge.schema.render_result import CandidateRejected, RenderedGrid


class PipelineContext:
    def __init__(self, image: bytes, scene: Document):
        self.image = image
        self.scene = scene
        self.renders: dict[str, RenderedGrid | CandidateRejected] = {}
        self.reviews: dict[str, CriticReport] = {}
        self.around: dict[str, bytes | None] = {}

    @classmethod
    def start(cls, image: bytes) -> PipelineContext:
        return cls(image, Document(DocumentHistory(name="scene")))

    @classmethod
    def from_snapshot(cls, snapshot: PipelineSnapshot) -> PipelineContext:
        context = cls(snapshot.image, Document(snapshot.scene))
        context.renders = dict(snapshot.renders)
        context.reviews = dict(snapshot.reviews)
        return context

    def snapshot(self) -> PipelineSnapshot:
        return PipelineSnapshot(image=self.image, scene=self.scene.history, renders=self.renders,
                                reviews=self.reviews)

    def best_revision(self) -> str | None:
        if self.reviews:
            return max(self.reviews, key=lambda revision: self.reviews[revision].score)
        rendered = [revision for revision, outcome in self.renders.items() if isinstance(outcome, RenderedGrid)]
        return rendered[0] if rendered else None

    def twin(self, revision: str, among: Iterable[str]) -> str | None:
        text = self.scene.text_at(revision)
        return next((other for other in among if other != revision and self.scene.text_at(other) == text), None)
