"""会话管理与面试详情接口响应模型。"""

from pydantic import BaseModel, Field


class SessionItem(BaseModel):
    """会话基础信息。"""

    # 会话主键ID。
    id: int
    # 会话模式：0=学习，1=面试，2=笔记。
    session_model: int
    # 会话标题。
    title: str
    # 创建时间（Unix 秒）。
    created_at: int


class SessionListResponse(BaseModel):
    """会话分页列表响应。"""

    # 当前页码（从1开始）。
    page: int
    # 每页大小。
    page_size: int
    # 总记录数。
    total: int
    # 是否还有下一页。
    has_more: bool
    # 当前页会话数据。
    sessions: list[SessionItem]


class SessionCreateRequest(BaseModel):
    """创建会话请求体。"""

    # 会话模式：0=学习，1=面试，2=笔记。
    session_model: int = Field(default=1, ge=0, le=2)
    # 会话主题标题。
    title: str = Field(min_length=1, max_length=255)


class SessionCreateResponse(BaseModel):
    """创建会话响应体。"""

    # 创建结果文案。
    message: str
    # 新建会话数据。
    session: SessionItem


class SessionUpdateTitleRequest(BaseModel):
    """更新会话标题请求体。"""

    # 新标题。
    title: str = Field(min_length=1, max_length=255)


class SessionUpdateTitleResponse(BaseModel):
    """更新会话标题响应体。"""

    # 更新结果文案。
    message: str
    # 更新后的会话数据。
    session: SessionItem


class InterviewDetailResponse(BaseModel):
    """面试详情响应体。"""

    # 面试记录主键ID。
    id: int
    # 所属会话ID。
    session_id: int
    # 面试入口消息ID。
    message_id: int
    # 问答详情 JSON 数组。
    qa_object: list[dict]
    # 面试时长（秒）。
    interview_duration: int
    # 面试状态：0进行中 1已结束 2异常。
    status: int
    # 面试开始时间（Unix 秒）。
    created_at: int
    # 最后更新时间（Unix 秒）。
    updated_at: int

