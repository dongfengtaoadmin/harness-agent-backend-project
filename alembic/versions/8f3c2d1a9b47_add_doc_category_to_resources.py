"""add doc category to resources

Revision ID: 8f3c2d1a9b47
Revises: 5418bb08b3e6
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f3c2d1a9b47"
down_revision: Union[str, None] = "5418bb08b3e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column(
            "doc_category",
            sa.String(length=32),
            nullable=True,
            comment="文档业务分类：resume/study_material/general（仅文件类型有意义）",
        ),
    )
    op.create_index(
        "idx_user_id_doc_category",
        "resources",
        ["user_id", "doc_category"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_id_doc_category", table_name="resources")
    op.drop_column("resources", "doc_category")
