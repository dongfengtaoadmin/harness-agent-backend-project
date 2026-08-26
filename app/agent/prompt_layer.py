"""提示词层：统一组装 Prompt、记忆与链路上下文。

功能：
1. build_stream_chain_context  - 通用链路组装
2. build_personalized_prompt   - 带用户信息注入的个性化提示词
3. inject_user_info_to_template - 提示词动态填充

升级说明（0.3.x → 1.x）：
  旧写法：用 RunnableWithMessageHistory 包装链路，通过 configurable 传 session_id 管理历史。
  新写法：历史消息直接从 DB 加载后注入 prompt，链路本身只是 prompt | llm，更简单直接。
  安装：pip install langchain==1.3.4 langchain-core==1.4.2 langchain-openai==1.2.2 langchain-community==0.4.2 langchain-classic==1.0.7
"""

from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable
# [0.3.x] from langchain_core.runnables.history import RunnableWithMessageHistory
# [0.3.x] from langchain_classic.schema.runnable.history import RunnableWithMessageHistory
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm import get_chat_model
from app.agent.memory import build_chat_history_from_rows
# from app.agent.memory import get_latest_knowledge
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
) -> tuple[Runnable, dict[str, Any]]:
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

    # [1.x 新写法] 历史消息直接注入 inputs，链路本身只是 prompt | llm，无需 RunnableWithMessageHistory 包装。
    chain = prompt | get_chat_model(provider=provider)
    stream_inputs = {
        "history": history.messages,
        "user_input": request_text,
    }

    # [0.3.x 旧写法] RunnableWithMessageHistory 包装链路，通过 configurable 传 session_id。
    # history_store = {str(session_id): history}
    # def get_session_history(session_id_key: str):
    #     return history_store.setdefault(session_id_key, history)
    # chain = RunnableWithMessageHistory(
    #     prompt | get_chat_model(provider=provider),
    #     get_session_history,
    #     input_messages_key="user_input",
    #     history_messages_key="history",
    # )
    # stream_inputs = {
    #     "user_input": request_text,
    #     "local_kb": {...},
    #     "search_result": get_latest_knowledge(request_text),
    # }

    # stream_inputs["local_kb"] = {
    #     "Python": "基础语法、循环、函数、列表字典、文件操作、异常处理",
    #     "Java": "面向对象、集合、IO、多线程、Spring基础",
    #     "前端": "HTML/CSS、JS DOM、Vue、Ajax、响应式布局"
    # }
    # stream_inputs["search_result"] = get_latest_knowledge(request_text)

    return chain, stream_inputs


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
