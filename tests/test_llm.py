"""聊天模型 provider 路由测试。"""

from langchain_anthropic import ChatAnthropic

from app.agent.llm import get_chat_model


def test_default_provider_uses_glm5_anthropic() -> None:
    model = get_chat_model()
    assert isinstance(model, ChatAnthropic)
    assert model.model == "glm-5"


def test_legacy_deepseek_provider_also_uses_glm5_anthropic() -> None:
    model = get_chat_model("deepseek")
    assert isinstance(model, ChatAnthropic)
    assert model.model == "glm-5"
