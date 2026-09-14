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
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    reset_type = "DATETIME" if _is_sqlite else "TIMESTAMP WITH TIME ZONE"
    with engine.begin() as connection:
        if "language" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'en'"))
        if "plan" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN plan VARCHAR(16) NOT NULL DEFAULT 'free'"))
        if "credits" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 3"))
        if "credits_reset_at" not in user_columns:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN credits_reset_at {reset_type} NULL"))

        # Credit accounting migration: existing balances are conservatively
        # treated as subscription credits; top-up credits start at zero.
        if "subscription_credits" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN subscription_credits INTEGER NOT NULL DEFAULT 0"))
            connection.execute(text("UPDATE users SET subscription_credits = credits"))
        if "topup_credits" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN topup_credits INTEGER NOT NULL DEFAULT 0"))
        connection.execute(text("UPDATE users SET credits = subscription_credits + topup_credits"))

        if "payments" in tables:
            payment_columns = {column["name"] for column in inspector.get_columns("payments")}
            if "amount_usd_cents" not in payment_columns:
                connection.execute(text("ALTER TABLE payments ADD COLUMN amount_usd_cents INTEGER NULL"))

        if "usage_records" in tables:
            usage_columns = {column["name"] for column in inspector.get_columns("usage_records")}
            if "subscription_credits_reserved" not in usage_columns:
                connection.execute(
                    text(
                        "ALTER TABLE usage_records "
                        "ADD COLUMN subscription_credits_reserved INTEGER NOT NULL DEFAULT 0"
                    )
                )
                # Existing reservations cannot be reconstructed from source; keep
                # them compatible by treating the reserved amount as subscription credit.
                connection.execute(
                    text(
                        "UPDATE usage_records SET subscription_credits_reserved = credits_reserved "
                        "WHERE subscription_credits_reserved = 0"
                    )
                )
            if "topup_credits_reserved" not in usage_columns:
                connection.execute(
                    text("ALTER TABLE usage_records ADD COLUMN topup_credits_reserved INTEGER NOT NULL DEFAULT 0")
                )
