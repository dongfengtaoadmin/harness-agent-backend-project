"""幂等初始化内置提示词；可在应用启动时调用，也可作为脚本执行。"""

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

# 兼容 ``python app/db/init_prompts.py`` 直接执行。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.agent_prompts import AGENT_CONFIG, COMMON_PROMPT, PRIVATE_PROMPTS
from app.db.database import SessionLocal
from app.db.models import PromptTemplate


PROFILE_VARIABLES = [
    "target_job",
    "years_experience",
    "target_level",
    "target_skills",
    "weak_topics",
]


def _template_exists(
    db: Session,
    *,
    agent_name: str | None,
    scene: str,
    version: int = 1,
) -> bool:
    """以 agent、场景和版本判断种子模板是否已经初始化。"""
    statement = select(PromptTemplate.id).where(
        PromptTemplate.scene == scene,
        PromptTemplate.version == version,
    )
    if agent_name is None:
        statement = statement.where(PromptTemplate.agent_name.is_(None))
    else:
        statement = statement.where(PromptTemplate.agent_name == agent_name)
    return db.scalar(statement.limit(1)) is not None


def initialize_prompt_templates(db: Session) -> int:
    """补齐缺失的内置 v1 模板，返回本次新增数量。

    已存在的模板不会更新或重复插入，因此可在每次应用启动时安全调用。
    """
    created = 0
    variables_json = json.dumps(PROFILE_VARIABLES, ensure_ascii=False)

    try:
        for agent_name, config in AGENT_CONFIG.items():
            scene = config["scene"]

            if not _template_exists(db, agent_name=None, scene=scene):
                db.add(
                    PromptTemplate(
                        agent_name=None,
                        scene=scene,
                        template_type=2,
                        name=f"{config['name']}公共规则",
                        description="系统内置初始版本",
                        template_content=COMMON_PROMPT,
                        variables=variables_json,
                        version=1,
                        is_active=1,
                    )
                )
                created += 1

            if not _template_exists(db, agent_name=agent_name, scene=scene):
                db.add(
                    PromptTemplate(
                        agent_name=agent_name,
                        scene=scene,
                        template_type=1,
                        name=config["name"],
                        description="系统内置初始版本",
                        template_content=PRIVATE_PROMPTS[agent_name],
                        variables=variables_json,
                        version=1,
                        is_active=1,
                    )
                )
                created += 1

        db.commit()
        return created
    except Exception:
        db.rollback()
        raise


def main() -> None:
    """命令行初始化入口。"""
    with SessionLocal() as db:
        created = initialize_prompt_templates(db)
    print(f"提示词初始化完成：新增 {created} 条，已存在的模板已跳过。")


if __name__ == "__main__":
    main()

