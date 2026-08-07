"""聊天消息查询与会话删除服务。"""

from minio.error import S3Error
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import raise_error
from app.core.logging_config import main_logger
from app.db.models import ChatMessage, Interview, Resource, Session as SessionModel
from app.schemas.chat_schemas import ChatMessageItem
from app.services.minio_storage_service import MinioStorageService

# 允许回传到前端的附件类型白名单。
ALLOWED_SEGMENT_TYPES = {"file", "image", "audio"}


class ChatService:
    """聊天相关业务服务。"""

    @staticmethod
    def get_session_messages(
        db: Session,
        user_id: int,
        session_id: int,
        page: int,
        page_size: int,
        session_model: int | None = None,
    ) -> tuple[list[ChatMessageItem], bool]:
        """
        分页查询会话消息。

        说明：
        - request_text/response_text 始终作为正文字段返回；
        - request_segments/response_segments 仅返回附件段（file/image/audio）；
        - 查询按 created_at 倒序分页，再在单页内反转为升序，减少前端插入抖动。
        """
        ChatService._ensure_session_belongs_to_user(
            db=db, session_id=session_id, user_id=user_id, session_model=session_model
        )

        total_stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session_id,
            ChatMessage.user_id == user_id,
        )
        total = db.scalar(total_stmt) or 0

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(db.scalars(stmt))
        has_more = page * page_size < total

        # 单页按升序返回，减少前端渲染抖动；全局时序仍由前端 created_at 二次排序兜底。
        rows.reverse()
        messages = [
            ChatMessageItem(
                id=row.id,
                status=row.status,
                interview_id=row.interview_id,
                request_text=row.request_text,
                response_text=row.response_text,
                request_segments=ChatService._build_segments(
                    row.request_segments),
                response_segments=ChatService._build_segments(
                    row.response_segments),
                created_at=row.created_at,
            )
            for row in rows
        ]
        return messages, has_more

    @staticmethod
    def delete_session(
        db: Session, user_id: int, session_id: int, session_model: int | None = None
    ) -> tuple[int, int, int]:
        """
        删除会话与其关联消息/面试记录，并回收当前会话附件资源。

        返回：
        - deleted_messages: 删除消息数
        - deleted_interviews: 删除面试记录数
        - deleted_resources: 删除资源对象数（当前会话出现的 resource_id）
        """
        ChatService._ensure_session_belongs_to_user(
            db=db, session_id=session_id, user_id=user_id, session_model=session_model
        )

        msg_stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id, ChatMessage.user_id == user_id
        )
        messages = list(db.scalars(msg_stmt))
        message_count = len(messages)

        resource_ids = ChatService._collect_resource_ids(messages=messages)
        resource_paths_to_delete: list[str] = []
        deleted_resource_count = 0

        # 当前会话出现的 resource_id 直接删除。
        if resource_ids:
            resource_stmt = select(Resource).where(
                Resource.user_id == user_id,
                Resource.id.in_(resource_ids),
            )
            resources_to_delete = list(db.scalars(resource_stmt))
            resource_paths_to_delete = [
                item.storage_path for item in resources_to_delete]
            deleted_resource_count = len(resources_to_delete)
            for resource in resources_to_delete:
                db.delete(resource)

        interview_count_stmt = select(func.count(Interview.id)).where(
            Interview.session_id == session_id
        )
        # 删除面试记录
        interview_count = db.scalar(interview_count_stmt) or 0
        db.execute(delete(Interview).where(Interview.session_id == session_id))
        # 删除聊天消息
        db.execute(
            delete(ChatMessage).where(
                ChatMessage.session_id == session_id, ChatMessage.user_id == user_id
            )
        )
        # 删除会话消息
        db.execute(
            delete(SessionModel).where(
                SessionModel.id == session_id, SessionModel.user_id == user_id
            )
        )
        # 提交数据库事务
        db.commit()
        # 删除对象存储文件
        ChatService._delete_storage_objects(resource_paths_to_delete)
        return message_count, interview_count, deleted_resource_count

    @staticmethod
    def _build_segments(raw_segments: list[dict] | None) -> list[dict]:
        """
        仅返回附件段信息（file/image/audio），过滤无效项。

        注意：
        - 该函数不会拼接或改写 request_text/response_text；
        - 非 dict 项或未知 type 会被忽略。
        """
        if not raw_segments:
            return []

        result: list[dict] = []
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            segment_type = str(item.get("type", "")).strip().lower()
            if segment_type not in ALLOWED_SEGMENT_TYPES:
                continue
            result.append(item)
        return result

    @staticmethod
    def _collect_resource_ids(messages: list[ChatMessage]) -> set[int]:
        """
        从消息附件段提取 resource_id 集合。

        仅提取正整数 resource_id，用于删除会话时做资源回收判定。
        """
        resource_ids: set[int] = set()
        for message in messages:
            for segment in ChatService._build_segments(message.request_segments):
                resource_id = segment.get("resource_id")
                if isinstance(resource_id, int) and resource_id > 0:
                    resource_ids.add(resource_id)
            for segment in ChatService._build_segments(message.response_segments):
                resource_id = segment.get("resource_id")
                if isinstance(resource_id, int) and resource_id > 0:
                    resource_ids.add(resource_id)
        return resource_ids

    @staticmethod
    def _ensure_session_belongs_to_user(
        db: Session, session_id: int, user_id: int, session_model: int | None = None
    ) -> None:
        """会话存在性与归属校验，不通过时抛 404。"""
        stmt = select(SessionModel.id).where(
            SessionModel.id == session_id, SessionModel.user_id == user_id
        )
        if session_model is not None:
            stmt = stmt.where(SessionModel.session_model == session_model)
        found_id = db.scalar(stmt)
        if not found_id:
            raise_error(code=404, message="会话不存在")

    @staticmethod
    def _delete_storage_objects(storage_paths: list[str]) -> int:
        """
        删除 MinIO 对象，返回成功删除数量。

        说明：
        - 仅识别 minio://bucket/key 路径；
        - 删除失败仅记录日志，不回滚已提交的数据库事务。
        """
        if not storage_paths:
            return 0

        client = MinioStorageService.get_client()
        deleted = 0
        for storage_path in storage_paths:
            if not MinioStorageService.is_minio_storage_path(storage_path):
                continue
            try:
                MinioStorageService.delete_object_by_storage_path(
                    client=client, storage_path=storage_path, ignore_not_found=True
                )
                deleted += 1
            except S3Error as exc:
                main_logger.warning(
                    f"删除 MinIO 对象失败: {storage_path}, error={exc}")
            except Exception as exc:
                main_logger.warning(f"删除对象存储文件异常: {storage_path}, error={exc}")
        return deleted
