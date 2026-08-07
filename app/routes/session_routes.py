"""会话相关路由：负责参数接入、鉴权与响应组装，业务逻辑下沉到 service。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core import common_error_responses
from app.core.auth import get_current_user
from app.db import get_db
from app.db.models import User
from app.schemas import (
    ChatMessagePageResponse,
    DeleteSessionResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionItem,
    SessionListResponse,
    SessionUpdateTitleRequest,
    SessionUpdateTitleResponse,
    StreamChatRequest,
)
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.services.stream_chat_service import StreamChatService

router = APIRouter()
# 统一依赖别名：减少每个路由函数重复书写 Depends。
DBSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=SessionListResponse, responses=common_error_responses, summary="分页获取会话列表")
def list_sessions(
    db: DBSession,
    current_user: CurrentUser,
    session_model: Annotated[int, Query(ge=0, le=2, description="会话模式：0学习 1面试 2笔记")],
    page: Annotated[int, Query(ge=1, description="页码，从1开始")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页数量，1-100")] = 20,
) -> SessionListResponse:
    """分页获取当前用户在指定会话模式下的会话列表。"""
    sessions, total, has_more = SessionService.list_sessions(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        session_model=session_model,
    )
    return SessionListResponse(
        page=page,
        page_size=page_size,
        total=total,
        has_more=has_more,
        sessions=[
            SessionItem(
                id=item.id,
                session_model=item.session_model,
                title=item.title,
                created_at=item.created_at,
            )
            for item in sessions
        ],
    )


@router.post("", response_model=SessionCreateResponse, responses=common_error_responses, summary="创建会话")
def create_session(payload: SessionCreateRequest, db: DBSession, current_user: CurrentUser) -> SessionCreateResponse:
    """创建会话并返回标准化会话对象。"""
    session = SessionService.create_session(
        db=db,
        user_id=current_user.id,
        title=payload.title,
        session_model=payload.session_model,
    )
    return SessionCreateResponse(
        message="会话创建成功",
        session=SessionItem(
            id=session.id,
            session_model=session.session_model,
            title=session.title,
            created_at=session.created_at,
        ),
    )


@router.put("/{session_id}", response_model=SessionUpdateTitleResponse, responses=common_error_responses, summary="编辑会话标题")
def update_session_title(
    session_id: Annotated[int, Path(gt=0, description="会话ID")],
    payload: SessionUpdateTitleRequest,
    db: DBSession,
    current_user: CurrentUser,
    session_model: Annotated[int, Query(ge=0, le=2, description="会话模式：0学习 1面试 2笔记")],
) -> SessionUpdateTitleResponse:
    """更新会话标题；仅允许操作当前用户自己的会话。"""
    session = SessionService.update_session_title(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        title=payload.title,
        session_model=session_model,
    )
    return SessionUpdateTitleResponse(
        message="会话标题更新成功",
        session=SessionItem(
            id=session.id,
            session_model=session.session_model,
            title=session.title,
            created_at=session.created_at,
        ),
    )


@router.get(
    "/{session_id}/messages",
    response_model=ChatMessagePageResponse,
    response_model_exclude_none=True,
    responses=common_error_responses,
    summary="分页获取会话消息",
)
def get_session_messages(
    session_id: Annotated[int, Path(gt=0, description="会话ID")],
    db: DBSession,
    current_user: CurrentUser,
    session_model: Annotated[int, Query(ge=0, le=2, description="会话模式：0学习 1面试 2笔记")],
    page: Annotated[int, Query(ge=1, description="页码，从1开始")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页数量，1-100")] = 20,
) -> ChatMessagePageResponse:
    """分页获取会话消息（按页返回，便于前端滚动加载）。"""
    messages, has_more = ChatService.get_session_messages(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        page=page,
        page_size=page_size,
        session_model=session_model,
    )
    return ChatMessagePageResponse(
        session_id=session_id,
        page=page,
        page_size=page_size,
        has_more=has_more,
        messages=messages,
    )


@router.post("/{session_id}/stream-chat", responses=common_error_responses, summary="单Agent流式对话")
async def stream_chat(
    session_id: Annotated[int, Path(gt=0, description="会话ID")],
    payload: StreamChatRequest,
    db: DBSession,
    current_user: CurrentUser,
    session_model: Annotated[int, Query(ge=0, le=2, description="会话模式：0学习 1面试 2笔记")],
    agent_name: Annotated[str, Query(description="智能体名称")] = "interview_host",
    scene: Annotated[str, Query(description="业务场景")] = "interview",
) -> StreamingResponse:
    """单 Agent 流式对话入口（SSE）。"""
    return StreamChatService.stream_chat(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        session_model=session_model,
        request_text=payload.request_text,
        select_model=payload.select_model,
        provider=payload.provider,
        agent_name=agent_name,
        scene=scene,
    )


@router.delete("/{session_id}", response_model=DeleteSessionResponse, responses=common_error_responses, summary="删除会话")
def delete_session(
    session_id: Annotated[int, Path(gt=0, description="会话ID")],
    db: DBSession,
    current_user: CurrentUser,
    session_model: Annotated[int, Query(ge=0, le=2, description="会话模式：0学习 1面试 2笔记")],
) -> DeleteSessionResponse:
    """删除会话及关联数据，并返回删除统计信息。"""
    deleted_messages, deleted_interviews, deleted_resources = ChatService.delete_session(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        session_model=session_model,
    )
    return DeleteSessionResponse(
        message="会话删除成功",
        session_id=session_id,
        deleted_messages=deleted_messages,
        deleted_interviews=deleted_interviews,
        deleted_resources=deleted_resources,
    )
