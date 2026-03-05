from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///mission_control.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def migrate_db() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "task" in table_names:
        task_columns = {col["name"] for col in inspector.get_columns("task")}
        if "updated_at" not in task_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE task ADD COLUMN updated_at TIMESTAMP"))
                conn.execute(
                    text("UPDATE task SET updated_at = created_at WHERE updated_at IS NULL")
                )


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    migrate_db()


def get_session() -> Session:
    return Session(engine)
