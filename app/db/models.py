import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(10), default="ru")
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_activated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    plan_expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_until: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_bot_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="direct")
    admin_note: Mapped[str | None] = mapped_column(Text)  # noqa: F821
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
