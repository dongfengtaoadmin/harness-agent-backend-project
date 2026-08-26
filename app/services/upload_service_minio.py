"""MinIO 上传服务：当前运行逻辑（生产路径）。"""

import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import raise_error
from app.core.settings import settings
from app.db.models import Resource, User
from app.rag import  infer_doc_category
from app.services.minio_storage_service import MinioStorageService

# 图片后缀与 MIME 白名单。
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
}

# 文档后缀与 MIME 白名单。
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# 音频后缀与 MIME 白名单。
ALLOWED_AUDIO_EXTENSIONS = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}

# 所有允许上传的后缀集合（按后缀映射到标准 MIME）。
ALLOWED_EXTENSIONS = {
    **ALLOWED_IMAGE_EXTENSIONS,
    **ALLOWED_DOCUMENT_EXTENSIONS,
    **ALLOWED_AUDIO_EXTENSIONS,
}

# 上传大小上限：10MB。
MAX_FILE_SIZE = 50 * 1024 * 1024

# 资源类型枚举：与 resources.resource_type 对齐。
RESOURCE_TYPE_FILE = 0
RESOURCE_TYPE_IMAGE = 1
RESOURCE_TYPE_AUDIO = 2

# 存储场景枚举：与 resources.storage_scene 对齐。
STORAGE_SCENE_LONG = 0
STORAGE_SCENE_SHORT = 1
STORAGE_SCENE_EXTRACT_ONLY = 2
STORAGE_SCENE_PERMANENT = 3

# 支持的存储场景集合，用于参数校验。
SUPPORTED_STORAGE_SCENES = {
    STORAGE_SCENE_LONG,
    STORAGE_SCENE_SHORT,
    STORAGE_SCENE_EXTRACT_ONLY,
    STORAGE_SCENE_PERMANENT,
}

# 上传用途枚举：0 普通资源，1 用户头像。
UPLOAD_PURPOSE_GENERAL = 0
UPLOAD_PURPOSE_AVATAR = 1
SUPPORTED_UPLOAD_PURPOSES = {UPLOAD_PURPOSE_GENERAL, UPLOAD_PURPOSE_AVATAR}


class UploadService:
    """上传业务服务（MinIO 版本）。"""

    @staticmethod
    def save_file(
        db: Session,
        user: User,
        file: UploadFile,
        storage_scene: int = STORAGE_SCENE_LONG,
        upload_purpose: int = UPLOAD_PURPOSE_GENERAL,
        doc_category: str | None = None,
    ) -> tuple[Resource, bool]:
        """统一上传入口，返回 (resource, is_deduplicated)。"""
        # 1) 统一参数与文件校验，先拦截非法请求。
        file_ext, file_size = UploadService._validate_file(file=file)
        UploadService._validate_storage_scene(storage_scene=storage_scene)
        UploadService._validate_upload_purpose(upload_purpose=upload_purpose)

        # 2) 计算内容哈希，作为用户维度去重核心键。
        md5_hash = UploadService._calculate_md5(file.file)
        resource_type = UploadService._resolve_resource_type(file_ext=file_ext)
        # 3) 基于用户/类型/场景生成对象键与数据库存储路径。
        object_key = UploadService._build_object_key(
            user_id=user.id,
            md5_hash=md5_hash,
            file_ext=file_ext,
            resource_type=resource_type,
            storage_scene=storage_scene,
        )
        storage_path = UploadService._build_storage_path(
            object_key=object_key, storage_scene=storage_scene
        )
        expire_time = UploadService._build_expire_time(
            storage_scene=storage_scene)
        # 仅文件类型解析业务分类；图片/音频留 None。前端显式传值合法则采用，否则按文件名兜底。
        resolved_category = UploadService._resolve_doc_category(
            resource_type=resource_type,
            file_name=file.filename,
            explicit=doc_category,
        )

        # 4) 代码层预查重：命中则复用资源，只更新场景/用途/过期时间。
        existing = UploadService._get_existing_resource(
            db=db, user_id=user.id, file_hash=md5_hash)
        if existing:
            UploadService._refresh_existing_resource(
                db=db,
                resource=existing,
                user=user,
                storage_scene=storage_scene,
                upload_purpose=upload_purpose,
                expire_time=expire_time,
            )
            return existing, True

        # 5) 非“仅提取”场景才上传原文件到 MinIO。
        if storage_scene != STORAGE_SCENE_EXTRACT_ONLY:
            UploadService._upload_to_minio(
                file=file, file_size=file_size, object_key=object_key)

        # 6) 落库资源元数据，形成“数据库元数据 <-> MinIO 对象”映射。
        resource = Resource(
            resource_type=resource_type,
            storage_scene=storage_scene,
            upload_purpose=upload_purpose,
            file_name=file.filename,
            file_hash=md5_hash,
            storage_path=storage_path,
            doc_category=resolved_category,
            user_id=user.id,
            expire_time=expire_time,
        )
        db.add(resource)
        # 仅头像用途的图片才写入 users.avatar，避免普通图片误覆盖头像。
        if resource_type == RESOURCE_TYPE_IMAGE and upload_purpose == UPLOAD_PURPOSE_AVATAR:
            user.avatar = storage_path

        try:
            db.commit()
        except IntegrityError:
            # 并发写入时由唯一索引兜底，回查后返回已存在资源，保持幂等体验。
            db.rollback()
            existing = UploadService._get_existing_resource(
                db=db, user_id=user.id, file_hash=md5_hash)
            if existing:
                return existing, True
            raise_error(code=409, message="资源写入冲突，请重试")

        db.refresh(resource)
        return resource, False

    @staticmethod
    def _validate_file(file: UploadFile) -> tuple[str, int]:
        """校验文件名、后缀、MIME 与大小，返回 (后缀, 文件字节数)。"""
        if not file.filename:
            raise_error(code=400, message="文件名不能为空")
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise_error(code=400, message="不支持的文件类型")
        expected_content_type = ALLOWED_EXTENSIONS[file_ext]
        allowed_content_types = {
            expected_content_type, "application/octet-stream"}
        if file.content_type and file.content_type not in allowed_content_types:
            raise_error(code=400, message="文件扩展名与内容类型不匹配")
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        if file_size > MAX_FILE_SIZE:
            raise_error(
                code=413, message=f"文件大小不能超过 {MAX_FILE_SIZE // 1024 // 1024}MB")
        file.file.seek(0)
        return file_ext, file_size

    @staticmethod
    def _validate_storage_scene(storage_scene: int) -> None:
        """校验存储场景是否合法。"""
        if storage_scene not in SUPPORTED_STORAGE_SCENES:
            raise_error(code=400, message="不支持的存储场景")

    @staticmethod
    def _resolve_resource_type(file_ext: str) -> int:
        """根据扩展名解析资源类型。"""
        if file_ext in ALLOWED_IMAGE_EXTENSIONS:
            return RESOURCE_TYPE_IMAGE
        if file_ext in ALLOWED_AUDIO_EXTENSIONS:
            return RESOURCE_TYPE_AUDIO
        return RESOURCE_TYPE_FILE

    @staticmethod
    def _validate_upload_purpose(upload_purpose: int) -> None:
        """校验上传用途是否合法。"""
        if upload_purpose not in SUPPORTED_UPLOAD_PURPOSES:
            raise_error(code=400, message="不支持的上传用途")

    @staticmethod
    def _resolve_doc_category(
        resource_type: int,
        file_name: str | None,
        explicit: str | None,
    ) -> str | None:
        """
        解析业务分类：
        - 仅文件类型（resource_type=0）参与分类；图片/音频返回 None。
        - explicit 合法则采用；否则按文件名做中文关键字兜底推断。
        - 非法值（如手抖传 "abc"）一律拒绝，回退到自动推断，避免脏数据入库。
        """
        if resource_type != RESOURCE_TYPE_FILE:
            return None
        return infer_doc_category(explicit=explicit)

    @staticmethod
    def _build_object_key(
        user_id: int, md5_hash: str, file_ext: str, resource_type: int, storage_scene: int
    ) -> str:
        """构建 MinIO 对象键。"""
        # “仅提取”场景不需要真实对象键，保留虚拟路径用于追踪。
        if storage_scene == STORAGE_SCENE_EXTRACT_ONLY:
            return f"virtual/user_{user_id}/{md5_hash}{file_ext}"
        resource_folder = {
            RESOURCE_TYPE_FILE: "files",
            RESOURCE_TYPE_IMAGE: "images",
            RESOURCE_TYPE_AUDIO: "audios",
        }[resource_type]
        return f"user_{user_id}/{resource_folder}/{md5_hash}{file_ext}"

    @staticmethod
    def _build_storage_path(object_key: str, storage_scene: int) -> str:
        """构建写入数据库的 storage_path。"""
        if storage_scene == STORAGE_SCENE_EXTRACT_ONLY:
            return object_key
        return f"minio://{settings.minio_bucket}/{object_key}"

    @staticmethod
    def _build_expire_time(storage_scene: int) -> datetime | None:
        """根据存储场景生成过期时间。"""
        # 注意：datetime.utcnow() 得到的是 UTC 时间，如果直接存数据库会导致时间提前（因为与北京时间差8小时）。
        # 部分系统不支持 Asia/Shanghai，兼容写法采用 UTC+8 偏移，无需依赖 zoneinfo
        now = datetime.utcnow() + timedelta(hours=8)
        if storage_scene in {STORAGE_SCENE_SHORT, STORAGE_SCENE_EXTRACT_ONLY}:
            return now + timedelta(hours=2)
        if storage_scene == STORAGE_SCENE_LONG:
            return now + timedelta(days=30)
        return None

    @staticmethod
    def _upload_to_minio(file: UploadFile, file_size: int, object_key: str) -> None:
        """上传文件到 MinIO，并在 bucket 不存在时自动创建。"""
        client = MinioStorageService.get_client()
        try:
            MinioStorageService.put_object(
                client=client,
                bucket_name=settings.minio_bucket,
                object_name=object_key,
                data=file.file,
                length=file_size,
                content_type=file.content_type or "application/octet-stream",
                auto_create_bucket=True,
            )
        except S3Error:
            raise_error(code=500, message="MinIO 上传失败")
        except Exception:
            raise_error(code=500, message="对象存储服务不可用")
        file.file.seek(0)

    @staticmethod
    def _get_existing_resource(db: Session, user_id: int, file_hash: str) -> Resource | None:
        """按 (user_id, file_hash) 查询已存在资源。"""
        stmt = select(Resource).where(Resource.user_id ==
                                      user_id, Resource.file_hash == file_hash)
        return db.scalar(stmt)

    @staticmethod
    def _refresh_existing_resource(
        db: Session,
        resource: Resource,
        user: User,
        storage_scene: int,
        upload_purpose: int,
        expire_time: datetime | None,
    ) -> None:
        """更新已存在资源的场景/用途/过期时间，并处理图片头像同步。"""
        resource.storage_scene = storage_scene
        resource.upload_purpose = upload_purpose
        resource.expire_time = expire_time
        if resource.resource_type == RESOURCE_TYPE_IMAGE and upload_purpose == UPLOAD_PURPOSE_AVATAR:
            user.avatar = resource.storage_path
        db.commit()
        db.refresh(resource)

    @staticmethod
    def _calculate_md5(file_stream: BinaryIO) -> str:
        """流式计算 MD5 并重置游标。"""
        md5 = hashlib.md5()
        for chunk in iter(lambda: file_stream.read(4096), b""):
            md5.update(chunk)
        file_stream.seek(0)
        return md5.hexdigest()
