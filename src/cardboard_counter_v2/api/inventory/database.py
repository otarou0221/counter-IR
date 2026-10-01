"""APIコンテナだけが所有するSQLAlchemy接続。"""

from __future__ import annotations

from contextlib import contextmanager
import os
from collections.abc import Iterator

from sqlalchemy import Engine, URL, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from cardboard_counter_v2.api.inventory.models import Base
from cardboard_counter_v2.api.schema_version import CURRENT_SCHEMA_REVISION


class Database:
    def __init__(self, url: str | None = None) -> None:
        environment_url = os.environ.get("DATABASE_URL", "").strip()
        host = os.environ.get("POSTGRES_HOST", "").strip()
        if url is not None:
            self.url: str | URL | None = url.strip()
        elif environment_url:
            self.url = environment_url
        elif host:
            self.url = URL.create(
                "postgresql+psycopg",
                username=os.environ.get("POSTGRES_USER", "cardboard_api"),
                password=os.environ.get("POSTGRES_PASSWORD", ""),
                host=host,
                port=int(os.environ.get("POSTGRES_PORT", "5432")),
                database=os.environ.get("POSTGRES_DB", "cardboard_counter"),
            )
        else:
            self.url = None
        self.engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None
        if self.url is not None:
            self.engine = create_engine(self.url, pool_pre_ping=True)
            self._sessions = sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False,
            )

    @property
    def enabled(self) -> bool:
        return self.engine is not None

    def initialize(self) -> None:
        if self.engine is None:
            return
        if self.engine.dialect.name != "postgresql":
            # SQLiteは単体テスト専用。PostgreSQLだけをAlembic管理対象とする。
            Base.metadata.create_all(self.engine)
            return
        inspector = inspect(self.engine)
        if "alembic_version" not in inspector.get_table_names():
            raise RuntimeError(
                "DBマイグレーションが未実行です。"
                "`python -m cardboard_counter_v2.api.migration_cli db upgrade`"
                "を先に実行してください"
            )
        with self.engine.connect() as connection:
            revisions = set(connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars())
        if revisions != {CURRENT_SCHEMA_REVISION}:
            current = ", ".join(sorted(revisions)) or "未設定"
            raise RuntimeError(
                f"DBスキーマが古いです: {current}。"
                "DBマイグレーションを実行してください"
            )

    @contextmanager
    def session(self) -> Iterator[Session]:
        if self._sessions is None:
            raise RuntimeError("DATABASE_URLが設定されていません")
        database_session = self._sessions()
        try:
            yield database_session
            database_session.commit()
        except Exception:
            database_session.rollback()
            raise
        finally:
            database_session.close()

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
