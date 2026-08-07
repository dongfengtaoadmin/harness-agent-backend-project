"""应用配置：从分层 .env 与操作系统环境变量加载，供全局单例 `settings` 使用。"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


def _normalize_app_env(raw_env: str | None) -> str:
    """将原始 APP_ENV 归一为 `development` 或 `production`（prod/production 视为 production）。"""
    env = (raw_env or "").strip().lower()
    if env in {"prod", "production"}:
        return "production"
    return "development"


def _project_root() -> Path:
    """返回后端项目根目录（`app` 的上一级，用于定位 `.env.*` 文件）。"""
    return Path(__file__).resolve().parents[2]


def _load_layered_env() -> tuple[str, dict[str, Any]]:
    """
    读取 `项目根/.env.{app_env}` 并与 `os.environ` 合并（后者覆盖文件中的同名键）。

    返回: (标准化后的 app_env, 合并后的键值对)
    """
    app_env = _normalize_app_env(os.getenv("APP_ENV", "development"))
    root = _project_root()
    env_values = dotenv_values(root / f".env.{app_env}")
    merged = {**env_values, **os.environ}
    return app_env, merged


@dataclass(frozen=True)
class Settings:
    """
    不可变应用配置。通过 `from_env` 从环境构建；字段与 `.env` / 启动环境变量名对应见各字段注释。

    必填项在 `from_env` 内显式校验：MYSQL_URL、JWT_SECRET、MinIO 四元组等。
    """

    app_env: str  # 运行环境：development / production
    mysql_url: str  # SQLAlchemy 风格数据库连接串（如 mysql+pymysql://...）
    jwt_secret: str  # JWT 签名密钥
    jwt_algorithm: str  # JWT 算法，如 HS256
    jwt_access_expire_minutes: int  # Access Token 有效时长（分钟）
    jwt_refresh_expire_minutes: int  # Refresh Token 有效时长（分钟）
    minio_endpoint: str  # MinIO 服务地址（host:port，无协议）
    minio_access_key: str  # MinIO 访问 Key
    minio_secret_key: str  # MinIO 访问 Secret
    minio_bucket: str  # 默认存储桶名
    minio_secure: bool  # 是否对 MinIO 使用 HTTPS
    deepseek_api_key: str  # 兼容 OpenAI 接口的 API Key（如 DeepSeek），流式聊天必填
    deepseek_base_url: str  # 兼容 OpenAI 的 API Base URL
    deepseek_model: str  # 模型名，如 deepseek-chat
    deepseek_temperature: float  # 采样温度
    deepseek_max_tokens: int  # 单次补全最大 token 数
    redis_host: str  # Redis 服务器地址
    redis_port: int  # Redis 服务器端口
    redis_db: int  # Redis 数据库编号
    redis_password: str  # Redis 密码

    @staticmethod
    def from_env() -> "Settings":
        """
        从分层 env 与 `os.environ` 解析出 `Settings` 实例；缺必填项时抛出 `RuntimeError`。
        大模型相关项允许为空 Key（调用模型时再失败），与 MinIO/JWT/DB 策略不同处见代码分支。
        """
        app_env, values = _load_layered_env()

        mysql_url = str(values.get("MYSQL_URL", "")).strip()
        if not mysql_url:
            raise RuntimeError("Environment variable MYSQL_URL is required")

        jwt_secret = str(values.get("JWT_SECRET", "")).strip()
        if not jwt_secret:
            raise RuntimeError("Environment variable JWT_SECRET is required")

        minio_endpoint = str(values.get("MINIO_ENDPOINT", "127.0.0.1:9000")).strip()
        minio_access_key = str(values.get("MINIO_ACCESS_KEY", "minioadmin")).strip()
        minio_secret_key = str(values.get("MINIO_SECRET_KEY", "minioadmin")).strip()
        minio_bucket = str(values.get("MINIO_BUCKET", "ai-resources")).strip()
        if not minio_endpoint or not minio_access_key or not minio_secret_key or not minio_bucket:
            raise RuntimeError("MinIO config is incomplete")

        deepseek_api_key = str(values.get("DEEPSEEK_API_KEY", "")).strip()
        deepseek_base_url = str(values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).strip()
        deepseek_model = str(values.get("DEEPSEEK_MODEL", "deepseek-chat")).strip()
        deepseek_temperature = float(values.get("DEEPSEEK_TEMPERATURE", 0.7))
        deepseek_max_tokens = int(values.get("DEEPSEEK_MAX_TOKENS", 1024))

        return Settings(
            app_env=app_env,
            mysql_url=mysql_url,
            jwt_secret=jwt_secret,
            jwt_algorithm=str(values.get("JWT_ALGORITHM", "HS256")),
            jwt_access_expire_minutes=int(values.get("JWT_ACCESS_EXPIRE_MINUTES", 30)),
            jwt_refresh_expire_minutes=int(values.get("JWT_REFRESH_EXPIRE_MINUTES", 10080)),
            minio_endpoint=minio_endpoint,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            minio_bucket=minio_bucket,
            minio_secure=str(values.get("MINIO_SECURE", "false")).strip().lower() == "true",
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=deepseek_base_url,
            deepseek_model=deepseek_model,
            deepseek_temperature=deepseek_temperature,
            deepseek_max_tokens=deepseek_max_tokens,
            redis_host=str(values.get("REDIS_HOST", "127.0.0.1")).strip(),
            redis_port=int(values.get("REDIS_PORT", 6379)),
            redis_db=int(values.get("REDIS_DB", 0)),
            redis_password=str(values.get("REDIS_PASSWORD", "")).strip(),
        )


# 进程级单例：import 时即按当前 APP_ENV 加载
settings = Settings.from_env()
