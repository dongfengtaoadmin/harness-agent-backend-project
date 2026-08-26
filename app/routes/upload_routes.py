
"""上传路由：对外暴露统一资源上传接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db import User, get_db
from app.schemas import UploadResponse
from app.services.minio_storage_service import MinioStorageService
from app.services.rag_service import RagService
from app.services.upload_service_minio import (
    RESOURCE_TYPE_FILE,
    UPLOAD_PURPOSE_AVATAR,
    UploadService,
)

# 上传路由组，不单独设置前缀，由 main.py 统一挂载。
router = APIRouter()


@router.post(
    "/upload/file",
    summary="通用文件上传接口",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadResponse,
)
def upload_file(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    # 存储场景：0长过期，1短过期，2仅提取，3永久。
    storage_scene: Annotated[int, Form()] = 0,
    # 上传用途：0普通资源，1用户头像。仅头像用途会更新 users.avatar。
    upload_purpose: Annotated[int, Form()] = 0,
    # 文档业务分类：resume/study_material/general；不传则按文件名兜底推断。仅文件类型有效。
    doc_category: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    支持文件/图片/音频上传，自动完成类型识别、去重与资源记录管理。
    """
    # 业务逻辑全部在 service 层，路由仅做参数接入与响应组装。
    resource, is_deduplicated = UploadService.save_file(
        db=db,
        user=current_user,
        file=file,
        storage_scene=storage_scene,
        upload_purpose=upload_purpose,
        doc_category=doc_category,
    )

    # 文档类型直接摄入向量库，图片和音频跳过。
    if resource.resource_type == RESOURCE_TYPE_FILE:
        file.file.seek(0) # 将文件指针重置到开头0
        RagService.ingest_from_bytes(
            file_bytes=file.file.read(),
            file_name=file.filename,
            user_id=current_user.id,
            doc_category=resource.doc_category,
        )

    avatar_url: str | None = None
    if upload_purpose == UPLOAD_PURPOSE_AVATAR:
        avatar_url = MinioStorageService.get_presigned_url(resource.storage_path)
    return UploadResponse(
        message="文件上传成功",
        resource_id=resource.id,
        file_path=resource.storage_path,
        file_hash=resource.file_hash,
        resource_type=resource.resource_type,
        storage_scene=resource.storage_scene,
        upload_purpose=resource.upload_purpose,
        doc_category=resource.doc_category,
        expire_time=resource.expire_time,
        is_deduplicated=is_deduplicated,
        avatar_url=avatar_url,
    )
