"""模型工厂：统一创建聊天模型实例。"""

from collections.abc import Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.settings import settings


# provider -> 聊天模型构造函数。
LlmFactory = Callable[[], BaseChatModel]


def _build_glm5_chat() -> ChatAnthropic:
    """通过 Anthropic 兼容接口创建 GLM-5 聊天模型。"""
    if not settings.anthropic_auth_token:
        raise RuntimeError("未配置 ANTHROPIC_AUTH_TOKEN")
    if not settings.anthropic_base_url:
        raise RuntimeError("未配置 ANTHROPIC_BASE_URL")
    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_auth_token,
        base_url=settings.anthropic_base_url,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
        streaming=True,
    )


# 扩展口：后续新增 provider 只需在这里注册。
_PROVIDER_FACTORIES: dict[str, LlmFactory] = {
    "glm5": _build_glm5_chat,
    "anthropic": _build_glm5_chat,
    # 兼容旧前端传入的 provider=deepseek，实际统一路由到 GLM-5。
    "deepseek": _build_glm5_chat,
}


def get_chat_model(provider: str = "glm5") -> BaseChatModel:
    """按 provider 返回聊天模型实例。"""
    factory = _PROVIDER_FACTORIES.get(provider)
    if not factory:
        raise ValueError(f"Unsupported llm provider: {provider}")
    return factory()
