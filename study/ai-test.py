"""最基础的腾讯云 GLM-5 Anthropic 兼容接口调用示例。"""

from anthropic import Anthropic

from app.core.settings import settings


client = Anthropic(
    api_key=settings.anthropic_auth_token,
    base_url=settings.anthropic_base_url,
)


def ai_chat(
    messages: list[dict[str, str]],
    system_prompt: str = "你是友好的 AI 助手，简洁回答。",
) -> str:
    try:
        print("AI：", end="", flush=True)
        with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            answer = ""
            for text in stream.text_stream:
                answer += text
                print(text, end="", flush=True)
        print()
        return answer
    except Exception as exc:
        print(f"调用失败：{exc}")
        return ""


if __name__ == "__main__":
    history: list[dict[str, str]] = []
    print("开始多轮对话，输入 exit 退出。")

    while True:
        user_input = input("你：").strip()
        if user_input.lower() in {"exit", "quit", "退出"}:
            print("对话结束。")
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})
        assistant_reply = ai_chat(history)
        if assistant_reply:
            history.append({"role": "assistant", "content": assistant_reply})
        else:
            history.pop()
