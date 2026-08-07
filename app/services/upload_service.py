"""旧版本地文件上传服务（教学示例，不参与当前运行）。"""

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.models import User

# 规范一：定义文件类型白名单
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
}

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# 规范二：定义文件大小上限
MAX_FILE_SIZE = 10 * 1024 * 1024


class UploadService:
    @staticmethod
    def save_file(db: Session, user: User, file: UploadFile) -> str:
        """
        通用的文件保存服务，自动根据文件类型判断后续操作。
        """
        file_path_str = UploadService._save_file_to_disk(user=user, file=file)

        # 根据文件类型，决定是否执行“更新数据库”这个副作用
        file_ext = Path(file.filename).suffix.lower()
        if file_ext in ALLOWED_IMAGE_EXTENSIONS:
            user.avatar = file_path_str
            db.commit()
            db.refresh(user)

        return file_path_str

    @staticmethod
    def _save_file_to_disk(user: User, file: UploadFile) -> str:
        """
        通用的文件校验与物理存储逻辑。
        """
        file_ext = Path(file.filename).suffix.lower()
        is_image = file_ext in ALLOWED_IMAGE_EXTENSIONS
        is_document = file_ext in ALLOWED_DOCUMENT_EXTENSIONS

        # 1) 类型校验
        if not is_image and not is_document:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的文件类型",
            )

        # 2) 大小校验
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件大小不能超过 {MAX_FILE_SIZE // 1024 // 1024}MB",
            )
        file.file.seek(0)

        # 3) 按 MD5 落盘（用户目录）
        md5_hash = UploadService._calculate_md5(file.file)
        upload_dir = Path(f"uploads/user_{user.id}")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{md5_hash}{file_ext}"
        file_path = upload_dir / file_name

        if not file_path.exists():
            try:
                with open(file_path, "wb") as buffer:
                    buffer.write(file.file.read())
            except OSError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="无法保存文件",
                )

        return str(file_path).replace("\\", "/")

    @staticmethod
    def _calculate_md5(file_stream: BinaryIO) -> str:
        """计算文件流的 MD5 哈希值。"""
        md5 = hashlib.md5()
        for chunk in iter(lambda: file_stream.read(4096), b""):
            md5.update(chunk)
        file_stream.seek(0)
        return md5.hexdigest()
