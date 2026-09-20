from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import settings


class Base(DeclarativeBase):
    pass


_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine_kwargs = {"future": True}
if not _is_sqlite:
    engine_kwargs.update(
        pool_size=10,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

engine = create_engine(settings.database_url, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    from database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "users" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    reset_type = "DATETIME" if _is_sqlite else "TIMESTAMP WITH TIME ZONE"
    with engine.begin() as connection:
        if "language" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'en'"
                )
            )
        if "plan" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN plan VARCHAR(16) NOT NULL DEFAULT 'free'"
                )
            )
        if "credits" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN credits INTEGER NOT NULL DEFAULT 5"
                )
            )
        if "credits_reset_at" not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE users "
                    f"ADD COLUMN credits_reset_at {reset_type} NULL"
                )
            )

    timestamp_type = "DATETIME" if _is_sqlite else "TIMESTAMP WITH TIME ZONE"
    table_columns = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in ("subscriptions", "payments")
        if table in table_names
    }
    billing_columns = {
        "subscriptions": {
            "plan": "VARCHAR(16) NOT NULL DEFAULT 'free'",
            "status": "VARCHAR(24) NOT NULL DEFAULT 'active'",
            "starts_at": f"{timestamp_type} NULL",
            "expires_at": f"{timestamp_type} NULL",
            "updated_at": f"{timestamp_type} NULL",
        },
        "payments": {
            "plan": "VARCHAR(16) NOT NULL DEFAULT 'pro'",
            "amount_nano_ton": "BIGINT NOT NULL DEFAULT 0",
            "destination": "VARCHAR(255) NOT NULL DEFAULT ''",
            "memo": "VARCHAR(128) NOT NULL DEFAULT ''",
            "tx_hash": "VARCHAR(128) NULL",
            "status": "VARCHAR(24) NOT NULL DEFAULT 'pending'",
            "created_at": f"{timestamp_type} NULL",
            "confirmed_at": f"{timestamp_type} NULL",
        },
    }
    with engine.begin() as connection:
        for table, definitions in billing_columns.items():
            for name, definition in definitions.items():
                if table in table_columns and name not in table_columns[table]:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                        )
                    )

        # Model metadata declares tx_hash UNIQUE, but create_all() does not
        # retrofit constraints onto an already deployed payments table.
        # A partial unique index also permits multiple pending NULL hashes.
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tx_hash "
                "ON payments (tx_hash) WHERE tx_hash IS NOT NULL"
            )
        )
