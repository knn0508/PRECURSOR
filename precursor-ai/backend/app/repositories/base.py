import uuid
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Minimal CRUD repository. Commits are the repository's responsibility."""

    def __init__(self, db: Session, model: type[ModelT]):
        self.db = db
        self.model = model

    def get(self, obj_id: uuid.UUID) -> ModelT | None:
        return self.db.get(self.model, obj_id)

    def list(self, offset: int = 0, limit: int = 100) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        return list(self.db.scalars(stmt))

    def count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(self.model)) or 0

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
        self.db.commit()
