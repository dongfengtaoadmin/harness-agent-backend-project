import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import SessionLocal
from app.db.models import ChatMessage, Interview, Session, User


def main() -> None:
    db = SessionLocal()
    now = int(time.time())

    try:
        user = db.execute(select(User).order_by(User.id)).scalars().first()
        if user is None:
            user = User(
                username=f"seed_user_{now}",
                password="seed_password_hash",
                avatar=None,
                create_time=now,
            )
            db.add(user)
            db.flush()

        session_row = Session(
            user_id=user.id,
            session_model=1,
            title=f"示例面试会话_{now}",
            created_at=now,
        )
        db.add(session_row)
        db.flush()

        message_row = ChatMessage(
            user_id=user.id,
            session_id=session_row.id,
            select_model=4,
            request_id=uuid.uuid4().hex,
            request_text="请开始一轮 Python 后端面试。",
            response_text="好的，我们先从数据库事务隔离级别开始。",
            created_at=now,
        )
        db.add(message_row)
        db.flush()

        interview_row = Interview(
            session_id=session_row.id,
            message_id=message_row.id,
            qa_object=[
                {
                    "id": uuid.uuid4().hex,
                    "question": "请解释一下 MySQL 常见事务隔离级别。",
                    "answer": "常见有读未提交、读已提交、可重复读和串行化。",
                    "created_at": now,
                }
            ],
            interview_duration=120,
            status=0,
            created_at=now,
            updated_at=now,
        )
        db.add(interview_row)
        db.commit()

        print(
            {
                "user_id": user.id,
                "session_id": session_row.id,
                "message_id": message_row.id,
                "interview_id": interview_row.id,
            }
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
