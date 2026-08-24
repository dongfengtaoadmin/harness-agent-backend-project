import sys
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import settings


# 搜索工具
search = DuckDuckGoSearchRun(
    api_wrapper=DuckDuckGoSearchAPIWrapper(max_results=2)
)


def get_latest_knowledge(topic: str):
    # 限定搜索关键词，优先获取较新的权威内容
    query = (
        f"{topic} 2026年 大厂面试题 高频考点 技术官网 招聘要求 "
        "排除广告 排除2025年前旧文章"
    )
    try:
        raw_result = search.run(query)
    except Exception as exc:
        print(f"联网搜索失败，将使用本地知识库：{exc}")
        return "联网搜索暂不可用"

    # 简单清洗：过滤太短的无效内容
    if len(raw_result) < 50:
        return "无有效搜索结果"
    return raw_result


# 新增本地知识库
local_knowledge = {
    "Python": "基础语法、循环、函数、列表字典、文件操作、异常处理",
    "Java": "面向对象、集合、IO、多线程、Spring基础",
    "前端": "HTML/CSS、JS DOM、Vue、Ajax、响应式布局",
}

# 记忆存储仓库：存储用户对话历史记录
session_store = {}


def get_session_history(session_id: str):
    if session_id not in session_store:
        session_store[session_id] = ChatMessageHistory()
    return session_store[session_id]

# 1. 初始化大模型
llm = ChatAnthropic(
    model=settings.anthropic_model,
    api_key=settings.anthropic_auth_token,
    base_url=settings.anthropic_base_url,
    temperature=0.7,
    streaming=True
)

# 2. 定义提示词模板
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是专业面试题生成专家，优先使用[本地知识库]生成面试题。"
            "本地知识库：{local_kb}。"
            "最新搜索结果：{search_result}",
        ),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{user_input}"),
    ]
)

# 3. 构建执行链：提示词+大模型
chain = prompt | llm

# 封装成带历史记录的执行链
ai_with_memory = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="user_input",
    history_messages_key="history",
)

# 配置会话 ID（不同 ID 使用不同的对话历史）
user_session = {"configurable": {"session_id": "interview_user"}}

# 4. 主循环：用户跟AI对话交互
while True:
    user_req = input("你的需求(输入 exit 退出)：")
    if user_req.lower() == "exit":
        break

    # 调用搜索工具获取最新知识
    latest_info = get_latest_knowledge(user_req)
    print(latest_info, "搜索结果")

    # 调用 AI，流式输出结果
    for chunk in ai_with_memory.stream(
        {
            "user_input": user_req,
            "local_kb": local_knowledge,
            "search_result": latest_info,
        },
        config=user_session,
    ):
        print(chunk.content, end="", flush=True)
    print()
