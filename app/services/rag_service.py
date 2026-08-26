"""RAG 业务服务层：对接上传链路，上传时直接摄入。"""

import tempfile #创建临时文件
from pathlib import Path

from app.rag import IngestResult, ingest_file


class RagService:
    """RAG 知识库摄入服务。"""

    @staticmethod
    def ingest_from_bytes(
        file_bytes: bytes,
        file_name: str,
        user_id: int,
        doc_category: str | None = None,
    ) -> IngestResult:
        """上传时直接复用内存中的文件字节，零额外网络 I/O。"""
        suffix = Path(file_name).suffix.lower()

        # 把内存中的字节数据临时写到磁盘 ，让解析库能读取。
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            return ingest_file(
                file_path=tmp_path,
                user_id=user_id,
                doc_category=doc_category,
                original_file_name=file_name,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
