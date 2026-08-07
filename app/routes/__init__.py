from .auth_routes import router as auth_router
from .interview_routes import router as interview_router
from .session_routes import router as session_router
from .user_routes import router as user_router
from .upload_routes import router as upload_router
from .prompt_routes import router as prompt_router

__all__ = ["auth_router", "interview_router", "session_router", "user_router", "upload_router", "prompt_router"]
