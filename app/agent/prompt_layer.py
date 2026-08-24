"""提示词层：统一组装 Prompt、记忆与链路上下文。

功能：
1. 原有的build_stream_chain_context - 通用链路组装
2. 新增的build_personalized_prompt - 带用户信息注入的个性化提示词
3. 新增的inject_user_info_to_template - 提示词动态填充
"""

from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import get_chat_model
from app.agent.memory import build_chat_history_from_rows, get_latest_knowledge
from app.db.models import ChatMessage
from app.services.prompt_template_service import prompt_template_manager
from app.services.user_profile_service import UserProfileService
from app.utils.prompt_logger import log_personalized_prompt_generated


def build_stream_chain_context(
    db: Session,
    user_id: int,
    session_id: int,
    current_message_id: int,
    provider: str,
    request_text: str,
    system_prompt: Optional[str] = None,
) -> tuple[RunnableWithMessageHistory, dict[str, Any]]:
    """组装流式链路上下文，返回可执行链与输入变量。"""
    # 1) 取最近 N 条历史消息（倒序拉取再反转，保证时间升序注入 prompt）。
    history_limit = 10
    history_rows = list(
        db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_message_id,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(history_limit)
        )
    )
    history_rows.reverse()
    history = build_chat_history_from_rows(history_rows)
    history_store = {str(session_id): history}

    def get_session_history(session_id_key: str):
        return history_store.setdefault(session_id_key, history)

    # 2) system_prompt 为 None 时使用默认兜底提示词，确保链路始终可用。
    if system_prompt is None:
        system_prompt = "你是一个简洁、可靠的单Agent助手。优先直接回答问题，必要时结合检索信息。"

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{user_input}"),
        ]
    )

    chain = prompt | get_chat_model(provider=provider)
    chain_with_memory = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="user_input",
        history_messages_key="history",
    )
    # 3) search_result 实时检索补充外部知识，local_kb 作为本地知识备用。
    stream_inputs = {
        "user_input": request_text,
        "local_kb": {
            "Python": "基础语法、循环、函数、列表字典、文件操作、异常处理",
            "Java": "面向对象、集合、IO、多线程、Spring基础",
            "前端": "HTML/CSS、JS DOM、Vue、Ajax、响应式布局"
        },
        "search_result": get_latest_knowledge(request_text),
    }
    return chain_with_memory, stream_inputs


def inject_user_info_to_template(
    template_content: str, # 参数1：完整的模板内容（含占位符）
    user_info_dict: dict,# 参数2：用户信息字典（格式化后的）
) -> str:
    """第三层：执行提示词注入 - 替换模板中的占位符为用户信息。"""
    prompt_content = template_content
    
    # 遍历字典的每个键值对
    for key, value in user_info_dict.items():
        # 构造占位符：{target_job}
        placeholder = "{" + key + "}"
        # 检查占位符是否存在
        if placeholder in prompt_content:
            # 替换占位符
            prompt_content = prompt_content.replace(placeholder, str(value))
    
    return prompt_content # 返回替换完成的提示词


def validate_user_info(user_info_dict: dict) -> dict:
    """第一层：验证 - 检查用户信息的有效性和安全性。"""
    FORBIDDEN_KEYWORDS = ["<script", "javascript:", "onclick", "prompt(", "eval("]
    MAX_LENGTH = {
        "target_job": 128,
        "years_experience": 64,
        "target_level": 32,
    }
    
    validated = {}
    for key, value in user_info_dict.items():
        if value is None:
            validated[key] = ""
            continue
        
        value_str = str(value)
        
        if key in MAX_LENGTH:
            max_len = MAX_LENGTH[key]
            if len(value_str) > max_len:
                value_str = value_str[:max_len]
        
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword.lower() in value_str.lower():
                raise ValueError(f"用户信息包含禁用内容: {keyword}")
        
        validated[key] = value_str
    
    return validated



# {
#     "name": "张三",
#     "age": 28,
#     "occupation": "Python 后端工程师",
#     "interests": ["人工智能", "健身"],
#     "response_preference": "内容简洁，并提供代码示例",
# }


# 你是一名专业的软件开发助手。

# 请根据以下用户资料调整回答方式：

# {{user_info}}

# 回答要求：
# 1. 准确回答用户的问题。
# 2. 根据用户的技术背景调整内容深度。
# 3. 尊重用户的表达偏好。

# 你是一名专业的软件开发助手。

# 请根据以下用户资料调整回答方式：

# 姓名：张三
# 年龄：28
# 职业：Python 后端工程师
# 兴趣：人工智能、健身
# 回答偏好：内容简洁，并提供代码示例

# 回答要求：
# 1. 准确回答用户的问题。
# 2. 根据用户的技术背景调整内容深度。
# 3. 尊重用户的表达偏好。

def build_personalized_prompt(
    db: Session,
    user_id: int,
    agent_name: str,
    scene: str,
) -> Optional[str]:
    """构建个性化提示词 - 完整的三层处理流程。
    
    流程：验证 → 格式化 → 注入
    """
    try:
        user_info = UserProfileService.get_profile_dict(db, user_id)
        validated_info = validate_user_info(user_info)
        formatted_info = UserProfileService.format_profile_for_injection(validated_info)
        
        full_prompt = prompt_template_manager.get_full_prompt(agent_name, scene, db)
        if not full_prompt:
            return None
        
        personalized_prompt = inject_user_info_to_template(full_prompt, formatted_info)
        
        log_personalized_prompt_generated(personalized_prompt, user_id, agent_name, scene)
        
        return personalized_prompt
        
    except Exception as e:
        raise RuntimeError(f"构建个性化提示词失败: {e}")
