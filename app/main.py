from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import register_exception_handlers
from app.core.logging_config import main_logger  # 导入日志配置
from app.db.base import Base
from app.db.database import SessionLocal, engine, get_db
from app.db.init_prompts import initialize_prompt_templates
from app.services.prompt_template_service import prompt_template_manager
# 导入 Base 和 engine
from app.routes import auth_router, interview_router, session_router, user_router, upload_router, prompt_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 为简化流程，使用 create_all() 自动创建表
    # 注意：生产环境推荐使用 Alembic 进行数据库版本管理
    Base.metadata.create_all(engine)
    # 幂等补齐内置提示词：首次写入，后续启动自动跳过已有版本。
    with SessionLocal() as db:
        created_count = initialize_prompt_templates(db)
        prompt_template_manager.load_all_effective_to_redis(db)
    main_logger.info(f"提示词初始化检查完成，本次新增 {created_count} 条")
    main_logger.info("应用启动完成，数据库表已确认就绪，请通过此地址访问: http://127.0.0.1:8000")
    yield


app = FastAPI(title="User CRUD API", version="1.0.0", lifespan=lifespan)
register_exception_handlers(app)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 允许前端开发环境跨域访问（本地 + 局域网）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://192.168.1.191:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 将用户相关接口统一挂载到 /users 前缀，便于路由分组与后续扩展版本。
app.include_router(user_router, prefix="/users", tags=["users"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(upload_router, tags=["upload"])
app.include_router(session_router, prefix="/sessions", tags=["sessions"])
app.include_router(interview_router, prefix="/interviews", tags=["interviews"])
app.include_router(prompt_router, prefix="/prompt", tags=["prompt_management"])


@app.get("/")
def root() -> dict[str, str]:
    # 入口信息接口：仅确认服务可访问。
    main_logger.debug("根路径接口被访问。")
    return {"message": "FastAPI user service is running"}


@app.get("/health/live", summary="服务存活检查", tags=["stability"])
def health_live() -> dict[str, str]:
    # liveness 仅检查服务进程是否正常对外响应。
    return {"status": "healthy", "service": "running"}


@app.get("/health/ready", summary="服务就绪检查", tags=["stability"])
def health_ready(db: Session = Depends(get_db)) -> dict[str, object]:
    # readiness 检查核心依赖（数据库）是否可用。
    result: dict[str, object] = {
        "status": "healthy",
        "details": {
            "service": "running",
            "database": "connected",
        },
    }
    try:
        db.execute(text("SELECT 1"))
        return result
    except Exception:
        result["status"] = "unhealthy"
        result["details"] = {
            "service": "running",
            "database": "disconnected",
        }
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=result,
        )
