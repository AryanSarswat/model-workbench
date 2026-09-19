"""SQLite persistence, per docs/architecture.md's data model.

Single-user, single-machine tool -- SQLite over Postgres because there's no server to run,
and over plain JSON files because this data needs real aggregation (unlike the test-case
dataset, which stays as hand-authored JSON on purpose).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "workbench.db"
engine = create_engine(f"sqlite:///{DB_PATH}")


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
