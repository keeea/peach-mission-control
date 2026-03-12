from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///mission_control.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def migrate_db() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "task" in table_names:
        task_columns = {col["name"] for col in inspector.get_columns("task")}
        with engine.begin() as conn:
            if "updated_at" not in task_columns:
                conn.execute(text("ALTER TABLE task ADD COLUMN updated_at TIMESTAMP"))
                conn.execute(
                    text("UPDATE task SET updated_at = created_at WHERE updated_at IS NULL")
                )
            if "sort_order" not in task_columns:
                conn.execute(text("ALTER TABLE task ADD COLUMN sort_order INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE task SET sort_order = id WHERE sort_order IS NULL"))


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    migrate_db()


def get_session() -> Session:
    return Session(engine)
