"""RAG 知识库构建领域工具：文件解析 → 分块 → 向量化 → Qdrant 写入。"""

from app.rag.core import (
    CATEGORY_GENERAL,
    CATEGORY_RESUME,
    CATEGORY_STUDY,
    SUPPORTED_CATEGORIES,
    SUPPORTED_EXTENSIONS,
    IngestResult,
    infer_doc_category,
    ingest_file,
)

__all__ = [
    "CATEGORY_GENERAL",
    "CATEGORY_RESUME",
    "CATEGORY_STUDY",
    "SUPPORTED_CATEGORIES",
    "SUPPORTED_EXTENSIONS",
    "IngestResult",
    "infer_doc_category",
    "ingest_file",
]
