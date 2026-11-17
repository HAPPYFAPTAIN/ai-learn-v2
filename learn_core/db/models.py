"""数据模型。

所有租户表都有 `tenant_id`，默认值取自会话变量 `app.tenant_id`；
行级安全策略由 Alembic 迁移统一启用，不在这里声明。
主键统一为 bigint identity，父表另有 UNIQUE (tenant_id, id)，
子表用 (tenant_id, parent_id) 复合外键，保证挂不到别的租户上。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID as PG_UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.sql import expression
from sqlmodel import Field, SQLModel

TS = DateTime(timezone=True)
TS_DEFAULT = sql_text("now()")


def ts_column(nullable: bool = False, default: bool = True) -> Column:
    return Column(TS, nullable=nullable, server_default=TS_DEFAULT if default else None)


def tenant_column() -> Column:
    """租户列：默认值从会话变量取，跨租户写入会被策略拒绝。"""
    return Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        server_default=sql_text("NULLIF(current_setting('app.tenant_id', true), '')::uuid"),
        index=True,
    )


def pk_column() -> Column:
    return Column(BigInteger, Identity(always=True), primary_key=True, nullable=False)


def uuid_pk_column() -> Column:
    return Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


class Tenant(SQLModel, table=True):
    """租户：官网用户 id 到内部租户的唯一映射。"""

    __tablename__ = "tenant"

    id: UUID = Field(sa_column=uuid_pk_column())
    official_user_id: str = Field(sa_column=Column(String(128), nullable=False, unique=True))
    status: str = Field(default="active", sa_column=Column(String(16), nullable=False, server_default="active"))
    quota_bytes: int = Field(
        default=5 * 1024**3,
        sa_column=Column(BigInteger, nullable=False, server_default=sql_text(str(5 * 1024**3))),
    )
    created_at: datetime = Field(sa_column=ts_column())
    last_seen_at: datetime = Field(sa_column=ts_column(nullable=True))


class TenantSetting(SQLModel, table=True):
    """每个租户的模型与预生成设置。"""

    __tablename__ = "tenant_setting"

    tenant_id: UUID = Field(sa_column=Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ))
    chat_model: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    reasoning: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    prep_ahead: int = Field(default=2, sa_column=Column(Integer, nullable=False, server_default="2"))
    updated_at: datetime = Field(sa_column=ts_column())


class CreationRequest(SQLModel, table=True):
    """Immutable creation receipt; retained until tenant deletion, including tombstones."""

    __tablename__ = "creation_request"
    __table_args__ = (UniqueConstraint("tenant_id", "operation", "request_id", name="uq_creation_request_intent"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    operation: str = Field(sa_column=Column(String(32), nullable=False))
    request_id: UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    payload_hash: str = Field(sa_column=Column(String(64), nullable=False))
    resource_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    response: dict = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(sa_column=ts_column())


class StoredFile(SQLModel, table=True):
    """文件存储的元数据；内容在 {files_root}/{tenant_id}/{kind}/{sha256}。"""

    __tablename__ = "stored_file"
    __table_args__ = (UniqueConstraint("tenant_id", "sha256", "kind", name="uq_stored_file_tenant_sha_kind"),)

    id: UUID = Field(sa_column=uuid_pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    kind: str = Field(sa_column=Column(String(16), nullable=False))
    sha256: str = Field(sa_column=Column(String(64), nullable=False))
    size_bytes: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, server_default="0"))
    storage_key: str = Field(sa_column=Column(Text, nullable=False))
    original_name: str = Field(
        default="", sa_column=Column(Text, nullable=False, server_default="")
    )
    created_at: datetime = Field(sa_column=ts_column())


class ModelCall(SQLModel, table=True):
    """一次模型调用的记账，用来和网关的计费逐条对账。"""

    __tablename__ = "model_call"
    __table_args__ = (Index("ix_model_call_tenant_created", "tenant_id", "created_at"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    event_id: str = Field(sa_column=Column(String(100), nullable=False, index=True))
    job_id: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    purpose: str = Field(default="", sa_column=Column(String(64), nullable=False, server_default=""))
    model: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    status: str = Field(default="ok", sa_column=Column(String(16), nullable=False, server_default="ok"))
    usage: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    created_at: datetime = Field(sa_column=ts_column())


class JobProgress(SQLModel, table=True):
    """任务进度；替代内存里的 prep._STATE。"""

    __tablename__ = "job_progress"
    __table_args__ = (UniqueConstraint("tenant_id", "job_id", name="uq_job_progress_tenant_job"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    job_id: str = Field(sa_column=Column(String(100), nullable=False))
    kind: str = Field(default="", sa_column=Column(String(32), nullable=False, server_default=""))
    subject: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    state: str = Field(default="queued", sa_column=Column(String(16), nullable=False, server_default="queued"))
    progress: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    updated_at: datetime = Field(sa_column=ts_column())


class AdaptSnapshot(SQLModel, table=True):
    """调整诊断快照；替代 data/adapt_snapshots/*.json。"""

    __tablename__ = "le_adapt_snapshot"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    data: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))


class ActionSession(SQLModel, table=True):
    """动作学习会话；替代隐藏的 action-learning.sqlite3。"""

    __tablename__ = "le_action_session"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    node_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    title: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    status: str = Field(default="open", sa_column=Column(String(16), nullable=False, server_default="open"))
    created_at: datetime = Field(sa_column=ts_column())
    updated_at: datetime = Field(sa_column=ts_column())


class ActionEvent(SQLModel, table=True):
    __tablename__ = "le_action_event"
    __table_args__ = (Index("ix_le_action_event_tenant_session", "tenant_id", "session_id"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    session_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    kind: str = Field(default="", sa_column=Column(String(32), nullable=False, server_default=""))
    payload: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    created_at: datetime = Field(sa_column=ts_column())


class MigrationRun(SQLModel, table=True):
    __tablename__ = "migration_run"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: Optional[UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True))
    source: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    status: str = Field(default="running", sa_column=Column(String(16), nullable=False, server_default="running"))
    report: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    started_at: datetime = Field(sa_column=ts_column())
    finished_at: datetime = Field(sa_column=ts_column(nullable=True))


class MigrationOrphan(SQLModel, table=True):
    """迁移时发现但挂不上父行的孤儿数据，保留原样，不静默删除。"""

    __tablename__ = "migration_orphan"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: Optional[UUID] = Field(default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True))
    table_name: str = Field(sa_column=Column(Text, nullable=False))
    row: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    created_at: datetime = Field(sa_column=ts_column())


class LlmLease(SQLModel, table=True):
    """模型调用的并发租约。

    每租户两条通道：交互（页面等待结果）和后台（生成、索引等工作）。
    交互优先给 2 个并发，后台 1 个，避免一次批量生成把页面挤死。
    用表而不是内存信号量，是因为 API 和 worker 是不同进程。
    """

    __tablename__ = "llm_lease"

    tenant_id: UUID = Field(sa_column=Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ))
    lane: str = Field(sa_column=Column(String(16), primary_key=True))
    holder: str = Field(sa_column=Column(String(100), primary_key=True))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


# ---------------------------------------------------------------- 学习业务表


class Project(SQLModel, table=True):
    __tablename__ = "le_project"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_le_project_tenant_id"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    title: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    topic: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    background: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    goal: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    weekly_hours: float = Field(default=10.0, sa_column=Column(Float, nullable=False, server_default="10"))
    roadmap_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")))
    status: str = Field(default="active", sa_column=Column(String(16), nullable=False, server_default="active"))
    created_at: datetime = Field(sa_column=ts_column())
    updated_at: datetime = Field(sa_column=ts_column())


class Knode(SQLModel, table=True):
    __tablename__ = "le_knode"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_le_knode_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["le_project.tenant_id", "le_project.id"],
            ondelete="CASCADE",
            name="fk_le_knode_project",
        ),
        Index("ix_le_knode_tenant_project", "tenant_id", "project_id"),
    )

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    code: str = Field(default="", sa_column=Column(String(32), nullable=False, server_default=""))
    title: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    description: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    stage: str = Field(default="base", sa_column=Column(String(16), nullable=False, server_default="base"))
    est_hours: float = Field(default=2.0, sa_column=Column(Float, nullable=False, server_default="2"))
    difficulty: int = Field(default=3, sa_column=Column(Integer, nullable=False, server_default="3"))
    mastery: float = Field(default=0.0, sa_column=Column(Float, nullable=False, server_default="0"))
    status: str = Field(default="pending", sa_column=Column(String(16), nullable=False, server_default="pending"))
    content_version: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    created_at: datetime = Field(sa_column=ts_column())


class KnodeCollection(SQLModel, table=True):
    """节点与 Kotaemon 资料集合的关联；替代逗号拼接的 collection_ids。"""

    __tablename__ = "le_knode_collection"

    tenant_id: UUID = Field(sa_column=Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ))
    node_id: int = Field(sa_column=Column(BigInteger, primary_key=True))
    collection_id: str = Field(sa_column=Column(String(64), primary_key=True))


class Kedge(SQLModel, table=True):
    __tablename__ = "le_kedge"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "project_id"],
            ["le_project.tenant_id", "le_project.id"],
            ondelete="CASCADE",
            name="fk_le_kedge_project",
        ),
        Index("ix_le_kedge_tenant_project", "tenant_id", "project_id"),
    )

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    source_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    target_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    relation: str = Field(default="prerequisite", sa_column=Column(String(16), nullable=False, server_default="prerequisite"))


class Card(SQLModel, table=True):
    __tablename__ = "le_card"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_le_card_tenant_id"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    node_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True, index=True))
    project_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    front: str = Field(sa_column=Column(Text, nullable=False))
    back: str = Field(sa_column=Column(Text, nullable=False))
    card_type: str = Field(default="basic", sa_column=Column(String(16), nullable=False, server_default="basic"))
    stability: float = Field(default=0.0, sa_column=Column(Float, nullable=False, server_default="0"))
    difficulty: float = Field(default=0.0, sa_column=Column(Float, nullable=False, server_default="0"))
    last_review: Optional[datetime] = Field(default=None, sa_column=Column(TS, nullable=True))
    next_review: datetime = Field(sa_column=ts_column())
    reps: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    step: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    state: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    due_order: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    suspended: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=expression.false()))
    created_at: datetime = Field(sa_column=ts_column())


class ReviewLog(SQLModel, table=True):
    __tablename__ = "le_reviewlog"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    card_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    rating: int = Field(sa_column=Column(Integer, nullable=False))
    state: int = Field(sa_column=Column(Integer, nullable=False))
    stability: float = Field(sa_column=Column(Float, nullable=False))
    difficulty: float = Field(sa_column=Column(Float, nullable=False))
    reviewed_at: datetime = Field(sa_column=ts_column())


class Quiz(SQLModel, table=True):
    __tablename__ = "le_quiz"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_le_quiz_tenant_id"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    project_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    node_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    title: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    quiz_type: str = Field(default="mixed", sa_column=Column(String(16), nullable=False, server_default="mixed"))
    scope_node_ids: list[int] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(BigInteger), nullable=False, server_default=sql_text("'{}'")),
    )
    created_at: datetime = Field(sa_column=ts_column())


class QuizQuestion(SQLModel, table=True):
    __tablename__ = "le_quiz_question"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_le_quiz_question_tenant_id"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    quiz_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    node_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    qtype: str = Field(sa_column=Column(String(16), nullable=False))
    stem: str = Field(sa_column=Column(Text, nullable=False))
    options: list = Field(default_factory=list, sa_column=Column(JSONB, nullable=False, server_default=sql_text("'[]'::jsonb")))
    answer: str = Field(sa_column=Column(Text, nullable=False))
    explanation: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    difficulty: int = Field(default=3, sa_column=Column(Integer, nullable=False, server_default="3"))


class QuizAttempt(SQLModel, table=True):
    __tablename__ = "le_quiz_attempt"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    question_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    user_answer: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    is_correct: Optional[bool] = Field(default=None, sa_column=Column(Boolean, nullable=True))
    feedback: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    attempted_at: datetime = Field(sa_column=ts_column())


class ProgressRecord(SQLModel, table=True):
    __tablename__ = "le_progress"
    __table_args__ = (Index("ix_le_progress_tenant_project", "tenant_id", "project_id"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    node_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    metric: str = Field(sa_column=Column(String(32), nullable=False))
    value: float = Field(default=0.0, sa_column=Column(Float, nullable=False, server_default="0"))
    recorded_at: datetime = Field(sa_column=ts_column())


class Task(SQLModel, table=True):
    __tablename__ = "le_task"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    node_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    title: str = Field(sa_column=Column(Text, nullable=False))
    description: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    task_type: str = Field(default="practice", sa_column=Column(String(16), nullable=False, server_default="practice"))
    status: str = Field(default="pending", sa_column=Column(String(16), nullable=False, server_default="pending"))
    output: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    created_at: datetime = Field(sa_column=ts_column())


class DailyReport(SQLModel, table=True):
    __tablename__ = "le_daily_report"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    project_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    report_date: datetime = Field(sa_column=Column(TS, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    study_minutes: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    cards_reviewed: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    nodes_progressed: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    created_at: datetime = Field(sa_column=ts_column())


class Note(SQLModel, table=True):
    __tablename__ = "le_note"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    node_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    content: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    selection: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    created_at: datetime = Field(sa_column=ts_column())
    updated_at: datetime = Field(sa_column=ts_column())


class Annotation(SQLModel, table=True):
    __tablename__ = "le_annotation"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    node_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    quote: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    body: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    created_at: datetime = Field(sa_column=ts_column())


class Resource(SQLModel, table=True):
    __tablename__ = "le_resource"

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    node_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    title: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    url: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    rtype: str = Field(default="doc", sa_column=Column(String(16), nullable=False, server_default="doc"))
    description: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    preview: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    source: str = Field(default="ai", sa_column=Column(String(16), nullable=False, server_default="ai"))
    created_at: datetime = Field(sa_column=ts_column())


class LessonGate(SQLModel, table=True):
    __tablename__ = "le_gate"
    __table_args__ = (UniqueConstraint("tenant_id", "node_id", name="uq_le_gate_tenant_node"),)

    id: Optional[int] = Field(default=None, sa_column=pk_column())
    tenant_id: UUID = Field(sa_column=tenant_column())
    user_id: str = Field(default="", sa_column=Column(String(128), nullable=False, server_default=""))
    node_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    project_id: int = Field(sa_column=Column(BigInteger, nullable=False, index=True))
    dwell_seconds: float = Field(default=0.0, sa_column=Column(Float, nullable=False, server_default="0"))
    quiz_correct: int = Field(default=-1, sa_column=Column(Integer, nullable=False, server_default="-1"))
    quiz_total: int = Field(default=3, sa_column=Column(Integer, nullable=False, server_default="3"))
    quiz_at: Optional[datetime] = Field(default=None, sa_column=Column(TS, nullable=True))
    recite_text: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    recite_passed: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default=expression.false()))
    recite_feedback: str = Field(default="", sa_column=Column(Text, nullable=False, server_default=""))
    passed_at: Optional[datetime] = Field(default=None, sa_column=Column(TS, nullable=True))
    created_at: datetime = Field(sa_column=ts_column())
    updated_at: datetime = Field(sa_column=ts_column())


# ---------------------------------------------------------------- RAG 存储


class RagChunk(SQLModel, table=True):
    """文档块与全文检索列；tsv 由 jieba 分词后写入。"""

    __tablename__ = "rag_chunk"
    __table_args__ = (Index("ix_rag_chunk_tsv", "tsv", postgresql_using="gin"),)

    tenant_id: UUID = Field(sa_column=Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ))
    index_id: str = Field(sa_column=Column(String(64), primary_key=True))
    chunk_id: str = Field(sa_column=Column(String(64), primary_key=True))
    source_id: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    text: str = Field(sa_column=Column(Text, nullable=False))
    metadata_: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")),
    )
    tsv: Optional[str] = Field(default=None, sa_column=Column(TSVECTOR, nullable=True))


class RagEmbedding(SQLModel, table=True):
    """384 维向量；HNSW 余弦索引在迁移里建。"""

    __tablename__ = "rag_embedding"

    tenant_id: UUID = Field(sa_column=Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ))
    index_id: str = Field(sa_column=Column(String(64), primary_key=True))
    chunk_id: str = Field(sa_column=Column(String(64), primary_key=True))
    source_id: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(Vector(384), nullable=True))


class LlmEventCounter(SQLModel, table=True):
    """每租户每种事件类型一个自增号，用于拼事件 id ``ln-j12-3-1``。

    用表而不是 sequence：租户是运行时建的，不可能为每个租户建 DDL 对象。
    """

    __tablename__ = "llm_event_counter"

    tenant_id: UUID = Field(sa_column=Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True,
    ))
    kind: str = Field(sa_column=Column(String(8), primary_key=True))
    value: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, server_default=sql_text("0")))
