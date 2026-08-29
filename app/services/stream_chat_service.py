"""轻量单Agent流式对话服务。"""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from typing import Any

from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from sqlalchemy.orm import Session

from app.agent.prompt_layer import build_stream_chain_context, build_personalized_prompt
from app.core.logging_config import main_logger
from app.db.models import ChatMessage
from app.services.session_service import SessionService
from app.utils.prompt_logger import log_chain_ready


def _sse_data(payload: dict[str, Any]) -> str:
    """将事件对象编码为一帧 SSE 文本。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class StreamChatService:
    """负责流式推送、历史重建与最终落库。"""

    @staticmethod
    def stream_chat(
        db: Session,
        user_id: int,
        session_id: int,
        session_model: int,
        request_text: str,
        select_model: int = 0,
        provider: str = "glm5",
        agent_name: str = "interview_host",
        scene: str = "interview",
    ) -> StreamingResponse:
        # 1) 会话归属校验，不存在则抛 404。
        SessionService.get_session_or_404(
            db=db,
            user_id=user_id,
            session_id=session_id,
            session_model=session_model,
        )

        # 2) 预写入消息占位行：先落库拿到 row.id，供历史记忆截断用。
        row = ChatMessage(
            user_id=user_id,
            session_id=session_id,
            select_model=select_model,
            request_id=uuid.uuid4().hex,
            request_text=request_text,
            response_text="",
            request_segments=[],
            response_segments=[],
            status=0,
            interview_id=None,
            file_extracted_text="",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        # 3) 构建个性化提示词（注入用户画像信息）；无模板时返回 None，由链路层使用默认提示词兜底。
        system_prompt = build_personalized_prompt(
            db=db,
            user_id=user_id,
            agent_name=agent_name,
            scene=scene,
        )

        log_chain_ready(user_id, session_id, agent_name, scene, provider, len(system_prompt) if system_prompt else 0)

        # 4) 组装链路上下文：历史记忆截断 + LLM 绑定 + 输入变量准备。
        chain_with_memory, stream_inputs = build_stream_chain_context(
            db=db,
            user_id=user_id,
            session_id=session_id,
            current_message_id=row.id,
            provider=provider,
            request_text=request_text,
            system_prompt=system_prompt,
        )

        def event_generator() -> Generator[str, None, None]:
            response_text = ""
            error_message = ""
            yield _sse_data({"type": "start", "message_id": row.id})
            try:
                # [1.x 新写法] 直接 stream，历史已在 inputs 中，无需 config 传 session_id。
                for chunk in chain_with_memory.stream(stream_inputs):
                    # [0.3.x 旧写法] config 用于让 RunnableWithMessageHistory 识别会话。
                    # for chunk in chain_with_memory.stream(
                    #     stream_inputs,
                    #     config={"configurable": {"session_id": str(session_id)}},
                    # ):
                    delta = StreamChatService._extract_text_delta(chunk)
                    if not delta:
                        continue
                    response_text += delta
                    yield _sse_data({"type": "delta", "text": delta})
            except Exception as exc:
                error_message = str(exc)
                main_logger.exception("stream_chat failed", exc_info=exc)
            finally:
                # 无论成功或异常，都将已积累的文本回写到占位行。
                row.response_text = response_text
                db.add(row)
                db.commit()

            if error_message:
                yield _sse_data({"type": "error", "message": error_message})
            yield _sse_data({"type": "done", "response_text": response_text})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @staticmethod
    def _extract_text_delta(chunk: Any) -> str:
        """从 LangChain 增量块中提取最终回答文本，忽略 Anthropic thinking 块。"""
        if isinstance(chunk, AIMessageChunk):
            # Anthropic 流式响应的 content 可能是 str，也可能是
            # [{"type": "thinking", ...}] / [{"type": "text", "text": ...}]。
            # LangChain 的 text 属性会只合并文本块，并始终可转为字符串。
            return str(chunk.text)
        return ""
