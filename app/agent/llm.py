"""模型工厂：统一创建聊天模型实例。"""

from collections.abc import Callable

from langchain_openai import ChatOpenAI

from app.core.settings import settings


# provider -> ChatOpenAI 构造函数。
LlmFactory = Callable[[], ChatOpenAI]


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


# 扩展口：后续新增 provider 只需在这里注册。
_PROVIDER_FACTORIES: dict[str, LlmFactory] = {
    "deepseek": _build_deepseek_chat,
}


def get_chat_model(provider: str = "deepseek") -> ChatOpenAI:
    """按 provider 返回聊天模型实例。"""
    factory = _PROVIDER_FACTORIES.get(provider)
    if not factory:
        raise ValueError(f"Unsupported llm provider: {provider}")
    return factory()
