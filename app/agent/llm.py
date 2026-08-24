"""模型工厂：统一创建聊天模型实例。"""

from collections.abc import Callable

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.core.settings import settings


# provider -> 聊天模型构造函数。
LlmFactory = Callable[[], ChatOpenAI | ChatAnthropic]


def _build_deepseek_chat() -> ChatOpenAI:
    """创建 DeepSeek(OpenAI兼容) 聊天模型。"""
    if not settings.deepseek_api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
        streaming=True,
    )


def _build_anthropic_chat() -> ChatAnthropic:
    """创建腾讯云 GLM-5（Anthropic 兼容接口）聊天模型。"""
    if not settings.anthropic_auth_token:
        raise RuntimeError("未配置 ANTHROPIC_AUTH_TOKEN")
    if not settings.anthropic_base_url:
        raise RuntimeError("未配置 ANTHROPIC_BASE_URL")
    return ChatAnthropic(
        model_name=settings.anthropic_model,
        api_key=settings.anthropic_auth_token,
        base_url=settings.anthropic_base_url,
        max_tokens_to_sample=settings.deepseek_max_tokens,
        temperature=settings.deepseek_temperature,
        streaming=True,
    )


# 扩展口：后续新增 provider 只需在这里注册。
_PROVIDER_FACTORIES: dict[str, LlmFactory] = {
    "anthropic": _build_anthropic_chat,
    # 兼容尚未更新的前端请求；旧 provider 值也统一切到腾讯云 GLM-5。
    "deepseek": _build_anthropic_chat,
}


def get_chat_model(provider: str = "anthropic") -> ChatOpenAI | ChatAnthropic:
    """按 provider 返回聊天模型实例。"""
    factory = _PROVIDER_FACTORIES.get(provider)
    if not factory:
        raise ValueError(f"Unsupported llm provider: {provider}")
    return factory()
