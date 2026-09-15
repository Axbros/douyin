from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint, JSON
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMBLOB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), server_default="CURRENT_TIMESTAMP(3)")
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), server_default="CURRENT_TIMESTAMP(3)", server_onupdate="CURRENT_TIMESTAMP(3)")
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    role: Mapped[str] = mapped_column(String(20))
    login: Mapped[str] = mapped_column(String(190), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    extra_douyin_account_quota: Mapped[int] = mapped_column(Integer, default=0)


class Script(TimestampMixin, Base):
    __tablename__ = "scripts"
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(150))
    content: Mapped[str] = mapped_column(String(500))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    review_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)


class Worker(TimestampMixin, Base):
    __tablename__ = "workers"
    worker_key: Mapped[str] = mapped_column(String(100), unique=True)
    hostname: Mapped[str] = mapped_column(String(255))
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="offline")
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cpu_percent: Mapped[float | None] = mapped_column(nullable=True)
    memory_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)


class DouyinAccount(TimestampMixin, Base):
    __tablename__ = "douyin_accounts"
    display_name: Mapped[str] = mapped_column(String(100))
    account_uid: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    assigned_customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ownership_type: Mapped[str] = mapped_column(String(20), default="platform")
    owner_customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="unlogged")
    enabled: Mapped[bool] = mapped_column(default=True)
    encrypted_storage_state: Mapped[bytes | None] = mapped_column(MEDIUMBLOB, nullable=True)
    storage_state_version: Mapped[int] = mapped_column(Integer, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    current_worker_id: Mapped[int | None] = mapped_column(ForeignKey("workers.id"), nullable=True)
    current_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    risk_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class AccountLoginSession(TimestampMixin, Base):
    __tablename__ = "account_login_sessions"
    account_id: Mapped[int] = mapped_column(ForeignKey("douyin_accounts.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    qr_payload: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3))
    scanned_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AccountLog(TimestampMixin, Base):
    __tablename__ = "account_logs"
    account_id: Mapped[int] = mapped_column(ForeignKey("douyin_accounts.id"))
    worker_id: Mapped[int | None] = mapped_column(ForeignKey("workers.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    room_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    target_account_count: Mapped[int] = mapped_column(Integer, default=3)
    account_source: Mapped[str] = mapped_column(String(20), default="platform")
    billing_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    script_order_mode: Mapped[str] = mapped_column(String(20), default="random")
    min_interval_seconds: Mapped[int] = mapped_column(Integer, default=20)
    max_interval_seconds: Mapped[int] = mapped_column(Integer, default=50)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class TaskScript(TimestampMixin, Base):
    __tablename__ = "task_scripts"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    script_id: Mapped[int] = mapped_column(ForeignKey("scripts.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("task_id", "script_id", name="uk_task_scripts_pair"),)


class TaskAccount(TimestampMixin, Base):
    __tablename__ = "task_accounts"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    account_id: Mapped[int] = mapped_column(ForeignKey("douyin_accounts.id"))
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), server_default="CURRENT_TIMESTAMP(3)")
    removed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class CommentLog(TimestampMixin, Base):
    __tablename__ = "comment_logs"
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("douyin_accounts.id"))
    room_id: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(String(500))
    result: Mapped[str] = mapped_column(String(40))
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sensitive_word: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)


class SensitiveWord(TimestampMixin, Base):
    __tablename__ = "sensitive_words"
    word: Mapped[str] = mapped_column(String(255), unique=True)
    match_type: Mapped[str] = mapped_column(String(20), default="contains")
    enabled: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"
    setting_key: Mapped[str] = mapped_column(String(100), unique=True)
    setting_value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
