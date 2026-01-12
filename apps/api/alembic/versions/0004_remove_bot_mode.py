"""Remove Telegram bot support

Revision ID: 0004_remove_bot_mode
Revises: 0003_add_image_cache
Create Date: 2026-01-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_remove_bot_mode"
down_revision = "0003_add_image_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("telegram_connections")}

    with op.batch_alter_table("telegram_connections") as batch_op:
        if "bot_token_encrypted" in columns:
            batch_op.drop_column("bot_token_encrypted")
        if "mode" in columns:
            batch_op.drop_column("mode")

    if bind and bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP TYPE IF EXISTS telegrammode"))


def downgrade() -> None:
    raise RuntimeError("Downgrade не поддерживается для удаления bot-режима")
