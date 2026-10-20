"""Enterprise-style customer-service agent built on Pydantic AI (MIT).

The agent follows a fixed policy: it must call the `recall` tool, answer only from what it returns, and decline when
nothing is returned. Every retrieval is recorded, so an incident knows which memories were in context.

Model selection (env `RIFFNEL_AGENT_MODEL` or the `model` argument):
- a Pydantic AI model string such as `anthropic:<model>` or `openai:<model>` runs a real LLM. NOT tested in this
  repository: it needs credentials, which the development environment does not have;
- unset: `OfflineStandIn`, a deterministic function that mimics the policy (calls `recall`, quotes the top memory).
  It is a test double, not a language model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import Agent, RunContext  # noqa: E402
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

SYSTEM_PROMPT = (
    "你是示例银行（仿真）的客服助手。回答前必须调用 recall 工具查询记忆；只能依据工具返回的内容回答，"
    "原样引用其中的数字与条件；若没有返回任何记忆，回答「抱歉，我没有相关信息。」，不要猜测。"
)


@dataclass
class Deps:
    store: object
    scope: dict
    k: int
    retrieved: list[str] = field(default_factory=list)


def _offline_policy(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Deterministic stand-in for an LLM that obeys SYSTEM_PROMPT."""
    last = messages[-1].parts[-1]
    if isinstance(last, ToolReturnPart):
        first = str(last.content).splitlines()[0] if str(last.content).strip() else ""
        text = first.split("] ", 1)[1] if first.startswith("[") and "] " in first else "抱歉，我没有相关信息。"
        return ModelResponse(parts=[TextPart(text)])
    question = next(p.content for m in messages for p in m.parts if p.part_kind == "user-prompt")
    return ModelResponse(parts=[ToolCallPart("recall", {"query": question})])


class EnterpriseBankAgent:
    """Same `answer(question, scope) -> (answer, retrieved_ids)` interface as the reference agent."""

    def __init__(self, store, model: str | None = None, k: int = 3, scope_filter: bool = True):
        self.store, self.k, self.scope_filter = store, k, scope_filter
        chosen = model or os.environ.get("RIFFNEL_AGENT_MODEL")
        self.model_name = chosen or "offline-stand-in"
        self.agent = Agent(chosen or FunctionModel(_offline_policy), deps_type=Deps, system_prompt=SYSTEM_PROMPT)

        @self.agent.tool
        def recall(ctx: RunContext[Deps], query: str) -> str:
            """Search the customer-service memory for facts about products, fees and customer history."""
            hits = ctx.deps.store.search(query, ctx.deps.scope if self.scope_filter else {}, ctx.deps.k)
            ctx.deps.retrieved.extend(r.id for r, _ in hits)
            return "\n".join(f"[{r.id}] {r.content}" for r, _ in hits)

    def answer(self, question: str, scope: dict) -> tuple[str, list[str]]:
        deps = Deps(self.store, scope, self.k)
        result = self.agent.run_sync(question, deps=deps)
        return str(result.output), list(dict.fromkeys(deps.retrieved))
