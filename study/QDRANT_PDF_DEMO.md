# 本地免费 PDF 向量检索 Demo

本示例使用 `BAAI/bge-small-zh-v1.5` 在本地生成 Embedding，并将向量保存到 Docker Qdrant。无需阿里云百炼、API Key 或模型调用费用。

## 处理流程

```text
读取 PDF → 清洗文字 → 分块 → BGE 本地生成向量 → 写入 Qdrant → 语义检索
```

## 1. 安装依赖

在项目根目录执行：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

核心依赖：

- `pypdf`：提取 PDF 文字
- `sentence-transformers`：本地加载 BGE 模型并生成向量
- `qdrant-client`：访问 Qdrant

## 2. 启动 Qdrant

```bash
docker compose up -d qdrant
docker compose ps qdrant
```

管理界面：http://127.0.0.1:6333/dashboard

## 3. 首次导入并检索

项目 `study` 目录已有示例 PDF，可以直接执行：

```bash
python study/qdrant_pdf_demo.py \
  --ingest \
  --query "这个候选人掌握哪些后端技术？"
```

首次运行会从 Hugging Face 下载约百兆的 BGE 模型到本机缓存，后续运行直接复用，不需要 API Key。

指定其他 PDF：

```bash
python study/qdrant_pdf_demo.py \
  --pdf "/绝对路径/文档.pdf" \
  --ingest \
  --query "文档主要讲了什么？"
```

## 4. 只检索已有数据

```bash
python study/qdrant_pdf_demo.py --query "项目中使用了哪些数据库？"
```

## 5. 重建学习集合

更换了 Embedding 模型或需要清空 Demo 数据时：

```bash
python study/qdrant_pdf_demo.py --ingest --recreate
```

集合名是 `study_pdf_chunks`。普通重复导入使用稳定向量 ID，会覆盖相同片段，不会重复累积；`--recreate` 会删除并重建这个 Demo 集合，请仅在确认不需要其中旧数据时使用。

## 注意事项

- 该 Demo 只负责“召回相关内容”，没有调用大语言模型生成答案。
- 扫描版 PDF 没有文字层，`pypdf` 无法提取，需要先 OCR。
- 本地 Qdrant 默认没有认证，只应绑定和用于可信的本地开发环境。
