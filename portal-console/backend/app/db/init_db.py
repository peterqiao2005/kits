from app import models  # noqa: F401
from app.db.base import Base
from app.db.compat import ensure_schema
from app.db.session import engine
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth import get_password_hash
from sqlalchemy import select
from sqlalchemy.orm import Session


def init_db(session: Session, username: str, password: str) -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema(session)
    session.commit()

    admin = session.scalar(select(User).where(User.username == username))
    if admin is None:
        session.add(
            User(
                username=username,
                password_hash=get_password_hash(password),
                role=UserRole.ADMIN,
            )
        )
        session.commit()
