from datetime import date, datetime
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


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str = ""
    status: TaskStatus = Field(default=TaskStatus.backlog)
    priority: TaskPriority = Field(default=TaskPriority.medium)
    owner: Owner = Field(default=Owner.joint)
    due_date: date | None = None
    project: str = "general"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    goal: str = ""
    status: ProjectStatus = Field(default=ProjectStatus.active)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobApplication(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company: str
    role: str
    stage: ApplicationStage = Field(default=ApplicationStage.discovered)
    url: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
