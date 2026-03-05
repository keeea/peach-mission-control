from datetime import UTC, date, datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class TaskStatus(str, Enum):
    backlog = "backlog"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Owner(str, Enum):
    lan = "lan"
    peach = "peach"
    joint = "joint"


class ProjectStatus(str, Enum):
    active = "active"
    paused = "paused"
    done = "done"


class ApplicationStage(str, Enum):
    discovered = "discovered"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str = ""
    status: TaskStatus = Field(default=TaskStatus.backlog)
    priority: TaskPriority = Field(default=TaskPriority.medium)
    owner: Owner = Field(default=Owner.joint)
    due_date: date | None = None
    project: str = "general"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    goal: str = ""
    status: ProjectStatus = Field(default=ProjectStatus.active)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobApplication(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company: str
    role: str
    stage: ApplicationStage = Field(default=ApplicationStage.discovered)
    url: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionToken(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    user_id: int = Field(index=True)
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ApprovalRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    action_type: str = "external_action"
    payload: str = ""
    status: ApprovalStatus = Field(default=ApprovalStatus.pending, index=True)
    requested_by: str = "system"
    reviewed_by: str = ""
    review_note: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    reviewed_at: datetime | None = None
