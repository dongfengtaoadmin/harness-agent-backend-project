"""MinIO 存储通用服务：统一客户端、路径解析、上传与删除。"""

from minio import Minio
from minio.error import S3Error

from app.core.settings import settings


class MinioStorageService:
    """统一封装 MinIO 常用操作，减少业务服务重复代码。"""

    @staticmethod
    def get_client() -> Minio:
        """创建 MinIO 客户端。"""
        return Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    @staticmethod
    def is_minio_storage_path(storage_path: str) -> bool:
        """判断路径是否为 minio://bucket/object_key 格式。"""
        return bool(storage_path and storage_path.startswith("minio://"))

    @staticmethod
    def parse_storage_path(storage_path: str) -> tuple[str, str]:
        """解析 minio://bucket/object_key 路径。"""
        if not MinioStorageService.is_minio_storage_path(storage_path):
            raise ValueError(f"非法 MinIO 存储路径: {storage_path}")
        path_body = storage_path[len("minio://") :]
        parts = path_body.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"非法 MinIO 存储路径: {storage_path}")
        return parts[0], parts[1]

    @staticmethod
    def ensure_bucket_exists(client: Minio, bucket_name: str) -> None:
        """确保 bucket 存在，不存在时自动创建。"""
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

    @staticmethod
    def put_object(
        client: Minio,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str,
        auto_create_bucket: bool = True,
    ) -> None:
        """上传对象到 MinIO。"""
        if auto_create_bucket:
            MinioStorageService.ensure_bucket_exists(client=client, bucket_name=bucket_name)
        client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            length=length,
            content_type=content_type,
        )

    @staticmethod
    def delete_object_by_storage_path(
        client: Minio, storage_path: str, ignore_not_found: bool = True
    ) -> bool:
        """
        通过 minio:// 路径删除对象。

        返回：
        - True: 删除成功或对象不存在(幂等成功)
        - False: 非 minio 路径（跳过）
        """
        if not MinioStorageService.is_minio_storage_path(storage_path):
            return False

        bucket_name, object_name = MinioStorageService.parse_storage_path(storage_path)
        try:
            client.remove_object(bucket_name=bucket_name, object_name=object_name)
            return True
        except S3Error as exc:
            if ignore_not_found and exc.code in {"NoSuchKey", "NoSuchObject"}:
                return True
            raise

