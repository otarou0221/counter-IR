from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from cardboard_counter_v2.api.inventory.database import Database
from cardboard_counter_v2.api.inventory.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError("オフラインDBマイグレーションには対応していません")


def run_migrations_online() -> None:
    database = Database()
    if database.engine is None:
        raise RuntimeError("PostgreSQL接続設定がありません")
    with database.engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    database.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
