"""面试详情路由：按 interview_id 查询面试记录。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core import common_error_responses
from app.core.auth import get_current_user
from app.db import get_db
from app.db.models import User
from app.schemas import InterviewDetailResponse
from app.services.session_service import SessionService

router = APIRouter()
# 统一数据库会话依赖类型，避免每个接口重复声明。
DBSession = Annotated[Session, Depends(get_db)]
# 统一当前登录用户依赖类型，确保数据按用户隔离。
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get(
    "/{interview_id}",
    response_model=InterviewDetailResponse,
    responses=common_error_responses,
    summary="获取面试详情",
)
def get_interview_detail(
    interview_id: Annotated[int, Path(gt=0, description="面试记录ID，必须大于0")],
    db: DBSession,
    current_user: CurrentUser,
) -> InterviewDetailResponse:
    """按 interview_id 获取面试详情文本信息。"""
    interview = SessionService.get_interview_detail(
        db=db, user_id=current_user.id, interview_id=interview_id
    )
    return InterviewDetailResponse(
        id=interview.id,
        session_id=interview.session_id,
        message_id=interview.message_id,
        qa_object=interview.qa_object,
        interview_duration=interview.interview_duration,
        status=interview.status,
        created_at=interview.created_at,
        updated_at=interview.updated_at,
    )
