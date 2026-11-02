from __future__ import annotations

import asyncio

from sceneforge.clients.llm import Llm, failure_usage, transient
from sceneforge.pipeline.budget import PromptBudget
from sceneforge.pipeline.diagnostics import log
from sceneforge.pipeline.scene_tools import SceneTools
from sceneforge.schema.agent_turn import AgentTurn
from sceneforge.schema.config import AgentConfig, RetryConfig
from sceneforge.schema.llm_reply import LlmReply
from sceneforge.schema.messages import AssistantMessage, InputImage, InputText, UserMessage
from sceneforge.schema.prompt_book import PromptBook
from sceneforge.schema.responses_api import Reasoning, ResponsesRequest, TokenUsage
from sceneforge.schema.session import Session


class Agent:
    def __init__(self, name: str, config: AgentConfig, llm: Llm, budget: PromptBudget,
                 tools: SceneTools | None = None, session_id: str | None = None, *, tag: str,
                 request_base: int = 0):
        self.name = name
        self.config = config
        self.tag = tag
        self._request_base = request_base
        self._next_input_tokens = 0
        self._llm = llm
        self._budget = budget
        self._tools = tools
        self._session_id = session_id
        self.session = self.new_session()

    @property
    def book(self) -> PromptBook:
        return self.config.prompts

    @property
    def max_read_replies(self) -> int:
        return self.config.scene_tools.max_read_replies if self.config.scene_tools else 0

    def new_session(self) -> Session:
        session_id = self._session_id if self.config.send_session_id else None
        return Session(instructions=self.book["SYSTEM"], session_id=session_id)

    async def ask(self, content: list[InputText | InputImage], retry: RetryConfig) -> AgentTurn:
        if not self.config.keep_history:
            self.session = self.new_session()
        self._begin_call()
        self.session.input.append(UserMessage(content=content))
        replies = [await self._reply(reading=True, retry=retry)]
        while self._only_reads(replies[-1]) and len(replies) <= self.max_read_replies and self._budget.can_call():
            self._begin_call()
            replies.append(await self._reply(reading=len(replies) < self.max_read_replies, retry=retry))
        return AgentTurn(replies=replies)

    def _begin_call(self) -> None:
        self._budget.begin_call(self.config.model, TokenUsage(input_tokens=self._next_input_tokens,
                                                              output_tokens=self.config.max_output_tokens))

    async def _reply(self, reading: bool, retry: RetryConfig) -> LlmReply:
        request = ResponsesRequest.from_session(
            self.session, self.config.model, Reasoning(effort=self.config.reasoning_effort),
            self.config.max_output_tokens, self._tools.specs(reading) if self._tools else [],
        )
        for attempt in range(retry.max_retries + 1):
            try:
                reply = await self._llm.call(request, self.session.session_id, self._request_base + attempt)
                break
            except Exception as error:
                self._budget.finish_call(self.config.model, failure_usage(error))
                if not transient(error) or attempt == retry.max_retries or not self._budget.can_call():
                    raise
                log(self.tag, f"{self.name}: provider failed transiently ({type(error).__name__}: {error}); "
                              f"retry {attempt + 1}/{retry.max_retries} in {retry.delay_ms} ms")
                await asyncio.sleep(retry.delay_ms / 1000)
                self._begin_call()
        self._budget.finish_call(self.config.model, reply.usage)
        if reply.usage is not None:
            self._next_input_tokens = reply.usage.input_tokens + reply.usage.output_tokens
        if reply.text:
            self.session.input.append(AssistantMessage(content=reply.text))
        if reply.function_calls and self._tools is None:
            raise RuntimeError(f"the {self.name} was offered no tools but its reply calls some")
        self.session.input += reply.function_calls
        self.session.input += [self._tools.run(call, self.name) for call in reply.function_calls]
        return reply

    def _only_reads(self, reply: LlmReply) -> bool:
        return (self._tools is not None and bool(reply.function_calls)
                and all(self._tools.is_read(call) for call in reply.function_calls))
