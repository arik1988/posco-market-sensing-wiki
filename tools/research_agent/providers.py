from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from .codex_model import CodexOAuthChatModel
from .settings import AgentSettings, ProviderId


def build_model(settings: AgentSettings) -> BaseChatModel:
    if settings.provider is ProviderId.CODEX:
        return CodexOAuthChatModel(
            model=settings.codex_model,
            reasoning_effort=settings.codex_effort,  # type: ignore[arg-type]
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.pgpt_model or "",
        api_key=settings.pgpt_token(),
        base_url=settings.pgpt_base_url,
        timeout=180,
        max_retries=1,
        streaming=False,
    )
