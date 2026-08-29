import sys
from pathlib import Path

from langchain_core.messages import AIMessageChunk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.stream_chat_service import StreamChatService


def test_extract_text_delta_from_string_content() -> None:
    chunk = AIMessageChunk(content="回答")
    assert StreamChatService._extract_text_delta(chunk) == "回答"


def test_extract_text_delta_ignores_thinking_blocks() -> None:
    chunk = AIMessageChunk(
        content=[
            {"type": "thinking", "thinking": "内部思考", "index": 0},
            {"type": "text", "text": "最终回答", "index": 1},
        ]
    )
    assert StreamChatService._extract_text_delta(chunk) == "最终回答"
