from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core import ErrorResponse
from app.core.auth import get_current_user
from app.db import get_db
from app.schemas import (
    UserCreateRequest,
    UserCreateResponse,
    UserDeleteResponse,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services import UserService

# 用户相关接口统一鉴权
router = APIRouter(dependencies=[Depends(get_current_user)])
# 统一声明数据库会话依赖类型，避免每个接口重复写 Depends(get_db)。
DBSession = Annotated[Session, Depends(get_db)]

# 统一错误响应模型声明，便于 Swagger 文档展示标准化错误结构。
common_error_responses = {
    400: {"model": ErrorResponse, "description": "请求参数错误"},
    401: {"model": ErrorResponse, "description": "未授权"},
    404: {"model": ErrorResponse, "description": "资源不存在"},
    409: {"model": ErrorResponse, "description": "资源冲突"},
    422: {"model": ErrorResponse, "description": "请求参数校验失败"},
    500: {"model": ErrorResponse, "description": "系统异常"},
}


@router.post(
    "",
    response_model=UserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses=common_error_responses,
)
def create_user(payload: UserCreateRequest, db: DBSession) -> UserCreateResponse:
    # 路由层只负责请求入参、依赖注入和响应封装，业务逻辑全部交给 service。
    user = UserService.create_user(db, payload)
    return UserCreateResponse(message="用户创建成功", user=user)


@router.get("", response_model=UserListResponse, responses=common_error_responses)
def list_users(db: DBSession) -> UserListResponse:
    # 统一包装为 { "users": [...] }，便于前端扩展分页信息。
    users = UserService.list_users(db)
    return UserListResponse(users=users)


@router.get("/{user_id}", response_model=UserResponse, responses=common_error_responses)
def get_user(
    user_id: Annotated[int, Path(gt=0, description="用户ID，必须大于0")],
    db: DBSession,
) -> UserResponse:
    # Path(gt=0) 在框架层先做参数校验，非法值不会进入业务层。
    return UserService.get_user(db, user_id)


@router.put("/{user_id}", response_model=UserResponse, responses=common_error_responses)
def update_user(
    user_id: Annotated[int, Path(gt=0, description="用户ID，必须大于0")],
    payload: UserUpdateRequest,
    db: DBSession,
) -> UserResponse:
    # 更新逻辑（唯一性、哈希、空请求校验）由 service 层集中处理。
    return UserService.update_user(db, user_id, payload)


@router.delete("/{user_id}", response_model=UserDeleteResponse, responses=common_error_responses)
def delete_user(
    user_id: Annotated[int, Path(gt=0, description="用户ID，必须大于0")],
    db: DBSession,
) -> UserDeleteResponse:
    # 删除成功后返回统一文案，前端可直接用于提示。
    UserService.delete_user(db, user_id)
    return UserDeleteResponse(message="用户删除成功")
