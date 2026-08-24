"""ChatAnthropic 动态调用工具的最小示例。"""

import sys
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool


# 允许直接执行：python study/dynamic_tool_agent.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import settings


@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    # 为了突出 Agent 逻辑，这里使用模拟数据，不调用真实天气接口。
    weather_data = {
        "北京": "晴，28℃",
        "上海": "小雨，26℃",
        "深圳": "多云，30℃",
    }
    return weather_data.get(city, f"暂时没有 {city} 的天气数据")


@tool
def add(a: int, b: int) -> int:
    """计算两个整数的和。"""
    return a + b


tools = [get_weather, add]
tool_map = {item.name: item for item in tools}


llm = ChatAnthropic(
    model=settings.anthropic_model,
    api_key=settings.anthropic_auth_token,
    base_url=settings.anthropic_base_url,
    temperature=0,
)

# 把工具说明交给模型，模型会根据用户问题自主选择是否调用工具。
agent = llm.bind_tools(tools)


def chat(user_input: str) -> str:
    messages = [HumanMessage(content=user_input)]

    # 最多执行 5 轮，防止模型无限调用工具。
    for _ in range(5):
        response = agent.invoke(messages)
        messages.append(response)

        print(response.tool_calls,'response')
        # 没有工具调用，说明模型已经得到答案。
        if not response.tool_calls:
            return str(response.content)

        # 执行模型自主选择的工具，再把结果交还给模型。
        for call in response.tool_calls:
            print(f"调用工具：{call['name']}，参数：{call['args']}")
            result = tool_map[call["name"]].invoke(call["args"])
            messages.append(
                ToolMessage(content=str(result), tool_call_id=call["id"])
            )

    return "执行步数过多，任务停止"


if __name__ == "__main__":
    question = input("你：")
    print("AI：", chat(question))
