"""第一、二步：读取 PDF 文本并进行智能分块。"""

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parent
PDF_PATH = BASE_DIR / "AI全栈智能体开发_个人简历.pdf"
CHUNK_SIZE = 500
OVERLAP = 50
MIN_CHUNK_SIZE = 20
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_NAME = "pdf_knowledge_chunks"


def extract_text_from_pdf(pdf_path: Path) -> str:
    """逐页读取 PDF，并返回合并后的文本。"""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")

    pages: list[str] = []

    with pdf_path.open("rb") as file:
        reader = PdfReader(file)

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text()

            if text and text.strip():
                pages.append(text.strip())
            else:
                print(f"第 {page_number} 页没有文字，已跳过")

    full_text = "\n".join(pages)

    # 清除零宽字符和 BOM。
    return re.sub(r"[\u200b\u200c\u200d\ufeff]", "", full_text)


def split_chunks(text: str) -> list[str]:
    """按指定长度切块，优先在句末截断，并保留上下文重叠。"""
    if CHUNK_SIZE <= 0 or OVERLAP < 0 or OVERLAP >= CHUNK_SIZE:
        raise ValueError("必须满足 CHUNK_SIZE > OVERLAP >= 0")

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    sentence_endings = "。！？!?；;\n"

    while start < text_length:
        end = min(start + CHUNK_SIZE, text_length)

        # 当前块不是最后一块时，向前寻找最近的句末，避免截断完整句子。
        if end < text_length:
            search_left = max(start + OVERLAP + 1, end - 100)
            for index in range(end - 1, search_left - 1, -1):
                if text[index] in sentence_endings:
                    end = index + 1
                    break

        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_SIZE:
            chunks.append(chunk)

        if end >= text_length:
            break

        # 下一块向前重叠一部分内容，同时保证游标一定向后推进。
        start = max(end - OVERLAP, start + 1)

    # 使用文本 MD5 指纹去重，同时保持原有顺序。
    seen: set[str] = set()
    unique_chunks: list[str] = []

    for chunk in chunks:
        fingerprint = hashlib.md5(chunk.encode("utf-8")).hexdigest()
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique_chunks.append(chunk)

    return unique_chunks


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """加载并缓存本地 Embedding 模型，避免重复加载。"""
    print(f"正在加载本地 Embedding 模型：{EMBEDDING_MODEL}")
    return SentenceTransformer(EMBEDDING_MODEL)


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """将文本块转换成向量；全程在本地运行，不需要 API Key。"""
    if not texts:
        return []

    embeddings = get_embedding_model().encode(
        texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    # 转成普通 Python 列表，便于后续写入 Qdrant。
    return embeddings.tolist()


def build_point_id(source: Path, chunk: str) -> str:
    """根据文件路径和文本生成稳定 UUID，避免重复写入。"""
    content = f"{source.resolve()}:{chunk}".encode("utf-8")
    digest = hashlib.sha256(content).digest()[:16]
    return str(UUID(bytes=digest))


def save_to_qdrant(
    chunks: list[str],
    vectors: list[list[float]],
    source: Path,
) -> int:
    """创建 Qdrant 集合，并保存文本块及对应向量。"""
    if not chunks:
        print("没有可写入的文本块")
        return 0
    if len(chunks) != len(vectors):
        raise ValueError("文本块数量与向量数量不一致")
    if not vectors[0]:
        raise ValueError("向量不能为空")

    vector_size = len(vectors[0])
    if any(len(vector) != vector_size for vector in vectors):
        raise ValueError("所有向量的维度必须一致")

    client = QdrantClient(url=QDRANT_URL)

    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"已创建 Qdrant 集合：{COLLECTION_NAME}")
    else:
        collection = client.get_collection(COLLECTION_NAME)
        configured_size = collection.config.params.vectors.size
        if configured_size != vector_size:
            raise ValueError(
                f"集合维度是 {configured_size}，当前向量维度是 {vector_size}，"
                "请更换集合名或删除旧集合后重试"
            )

    points = [
        models.PointStruct(
            id=build_point_id(source, chunk),
            vector=vector,
            payload={
                "source": source.name,
                "chunk_index": index,
                "text": chunk,
            },
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    # 真正负责判断新增还是覆盖
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
        wait=True,
    )
    print(f"写入完成：{len(points)} 个文本块")
    return len(points)


if __name__ == "__main__":
    pdf_text = extract_text_from_pdf(PDF_PATH)
    chunks = split_chunks(pdf_text)
    vectors = generate_embeddings(chunks)
    saved_count = save_to_qdrant(chunks, vectors, PDF_PATH)

    print(f"\nPDF 文本长度：{len(pdf_text)}")
    print(f"分块数量：{len(chunks)}")
    print(f"向量数量：{len(vectors)}")
    print(f"向量维度：{len(vectors[0]) if vectors else 0}")
    print(f"写入数量：{saved_count}")
