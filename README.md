# Agent Backend Project

基于 FastAPI、SQLAlchemy、MySQL、Redis、MinIO 和 LangChain 构建的智能面试后端服务，提供用户认证、会话管理、文件上传、提示词管理和流式对话等能力。

本文档以 **macOS + zsh** 为运行环境。

## 环境要求

- macOS
- Python 3.12（项目当前使用 3.12.13）
- MySQL
- Redis
- MinIO
- pyenv（推荐，用于管理 Python 版本）

## macOS 快速启动

### 1. 进入项目目录

```bash
cd /Users/apple/Desktop/code/Hermes/harness-hermes-multiagent-code/agent-backend-project
```

### 2. 选择 Python 版本

项目根目录已有 `.python-version` 时，pyenv 会自动选择对应版本。也可以手动设置：

```bash
pyenv local 3.12.13
python --version
```

预期输出：

```text
Python 3.12.13
```

### 3. 创建并激活虚拟环境

首次运行时创建虚拟环境：

```bash
python -m venv .venv
```

macOS 使用 `bin/activate` 激活：

```bash
source .venv/bin/activate
```

激活后，终端提示符通常会显示 `(.venv)`。也可以用下面的命令确认：

```bash
which python
```

输出路径应以项目中的 `.venv/bin/python` 结尾。

退出虚拟环境：

```bash
deactivate
```

> `.venv/Scripts/activate` 是 Windows 路径，不适用于 macOS。

### 4. 安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5. 配置环境变量

项目按照运行环境读取配置文件：

- 开发环境：`.env.development`
- 生产环境：`.env.production`

macOS 可先复制示例配置：

```bash
cp env.example .env.development
```

然后编辑 `.env.development`，至少检查以下配置：

```dotenv
APP_ENV=development

MYSQL_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/数据库名

JWT_SECRET=请替换为安全的随机字符串
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=120
JWT_REFRESH_EXPIRE_MINUTES=10080

MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=ai-resources
MINIO_SECURE=false

DEEPSEEK_API_KEY=请填写你的_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

在当前终端选择开发环境：

```bash
export APP_ENV=development
```

如果没有设置 `APP_ENV`，项目默认使用 `development`。操作系统环境变量会覆盖 `.env.development` 中的同名配置。

### 6. 启动服务

确保 MySQL、Redis 和 MinIO 已启动，然后执行：

```bash
export APP_ENV=development
uvicorn app.main:app --reload
```

也可以通过虚拟环境中的 Python 启动：

```bash
python -m uvicorn app.main:app --reload
```

服务默认地址：

- API：http://127.0.0.1:8000
- Swagger 文档：http://127.0.0.1:8000/docs
- ReDoc：http://127.0.0.1:8000/redoc
- 存活检查：http://127.0.0.1:8000/health/live
- 就绪检查：http://127.0.0.1:8000/health/ready

应用启动时会调用 SQLAlchemy `Base.metadata.create_all()` 创建尚不存在的数据表。

## 分层架构

项目采用职责分离的分层架构，请求的主要处理流程如下：

```text
客户端请求
    ↓
Routes 路由层
    ↓
Schemas 数据校验层
    ↓
Services 业务逻辑层
    ↓
DB 数据访问层
    ↓
MySQL / Redis / MinIO / LLM
```

### 各层职责

| 层级 | 目录 | 职责 |
| --- | --- | --- |
| 应用入口层 | `app/main.py` | 创建 FastAPI 应用、注册中间件和异常处理器、挂载路由、执行启动生命周期 |
| 路由层 | `app/routes/` | 定义 HTTP 接口，接收请求、注入依赖并调用业务服务；不应承载复杂业务逻辑 |
| 数据校验层 | `app/schemas/` | 使用 Pydantic 定义请求参数、响应数据及领域数据结构 |
| 业务服务层 | `app/services/` | 编排用户、会话、上传、提示词、聊天及资源清理等业务逻辑 |
| Agent 层 | `app/agent/` | 封装大模型调用、提示词处理和会话记忆能力 |
| 数据访问层 | `app/db/` | 管理 SQLAlchemy Engine、Session、ORM 基类和数据模型 |
| 核心基础设施层 | `app/core/` | 统一管理配置、认证、日志、限流、响应模型和全局异常处理 |
| 安全层 | `app/security.py` | 提供密码和令牌相关的安全能力 |
| 通用工具层 | `app/utils/` | 存放可复用且不属于具体业务的辅助工具 |
| 运维脚本 | `scripts/` | 存放数据初始化、资源清理等独立运行脚本 |
| 测试层 | `tests/` | 存放自动化测试和冒烟测试 |

### 项目目录

```text
agent-backend-project/
├── app/
│   ├── agent/                 # LLM、提示词和记忆能力
│   ├── core/                  # 配置、认证、日志、限流和异常处理
│   ├── db/                    # 数据库连接、ORM 基类和模型
│   ├── routes/                # FastAPI 路由
│   ├── schemas/               # Pydantic 请求/响应模型
│   ├── services/              # 业务逻辑服务
│   ├── utils/                 # 通用工具
│   ├── main.py                # 应用入口
│   └── security.py            # 密码与令牌安全工具
├── scripts/                   # 数据及资源维护脚本
├── tests/                     # 自动化测试
├── uploads/                   # 本地上传文件目录
├── alembic.ini                # Alembic 配置
├── env.example                # 环境变量示例
├── requirements.txt           # Python 依赖
└── README.md
```

### 分层开发约定

新增业务功能时，建议按以下顺序组织代码：

1. 在 `schemas/` 定义请求和响应模型。
2. 在 `services/` 编写业务规则及资源编排逻辑。
3. 在 `routes/` 定义接口并调用 Service。
4. 需要持久化时，在 `db/models.py` 定义或调整 ORM 模型。
5. 在 `tests/` 添加相应测试。

依赖方向应尽量保持为：`routes → services → db/agent`，避免数据库层反向依赖路由层。

## 数据库表结构管理

当前开发模式会在服务启动时通过 `create_all()` 自动创建新表，但它不会自动修改已经存在的表结构。

项目已有 `alembic.ini`，但使用 Alembic 前还需要确保项目中存在完整的迁移环境（例如 `alembic/env.py` 和 `alembic/versions/`）。迁移环境就绪后，可执行：

```bash
alembic revision --autogenerate -m "描述本次变更"
alembic upgrade head
```

生产环境推荐使用 Alembic 管理版本，不依赖 `create_all()` 完成表结构升级。

## 文件资源上传

上传接口：

```text
POST /upload/file
```

接口需要 Bearer Token，请求类型为 `multipart/form-data`。

主要字段：

- `file`：待上传文件，必填。
- `storage_scene`：存储场景，默认 `0`。
  - `0`：长过期，30 天。
  - `1`：短过期，2 小时。
  - `2`：仅提取内容，不保存原文件。
  - `3`：永久存储。
- `upload_purpose`：上传用途，默认 `0`。
  - `0`：普通资源。
  - `1`：用户头像；图片类型会更新用户头像。

当前上传实现会进行资源类型识别、用户级 MD5 去重，将文件保存到 MinIO，并把元数据写入数据库。实际运行逻辑位于 `app/services/upload_service_minio.py`。

## 资源清理脚本

只执行一次，适合手动验证：

```bash
python scripts/run_expired_resource_cleanup.py --once
```

持续运行，并在每天凌晨 03:00 清理：

```bash
python scripts/run_expired_resource_cleanup.py
```

可选参数：

- `--hour`：执行小时，默认 `3`。
- `--minute`：执行分钟，默认 `0`。
- `--timezone`：时区，默认 `Asia/Shanghai`。

## 测试

确保已激活虚拟环境并准备好测试环境配置，然后执行：

```bash
export APP_ENV=development
pytest
```

## 常见问题

### `pyenv: python: command not found`

为当前项目选择已安装的 Python 版本：

```bash
pyenv local 3.12.13
python --version
```

### 激活虚拟环境后没有显示 `(.venv)`

先确认环境是否实际激活：

```bash
echo $VIRTUAL_ENV
which python
```

如果设置过禁用提示符变量，可执行：

```bash
unset VIRTUAL_ENV_DISABLE_PROMPT
deactivate 2>/dev/null || true
source .venv/bin/activate
```

### 停止服务

在运行 Uvicorn 的终端按：

```text
Control + C
```
