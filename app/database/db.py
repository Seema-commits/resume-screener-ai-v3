from sqlalchemy import create_engine

from sqlalchemy.orm import (
    sessionmaker,
    declarative_base
)

from app.config import get_secret

# Required: logins, users and scan history live in the database.
# With no URL the app shows a clear error at startup.
DATABASE_URL = get_secret("DATABASE_URL")

# pool_pre_ping: Neon suspends idle databases, so check a pooled
# connection is still alive before using it.
engine = (
    create_engine(DATABASE_URL, pool_pre_ping=True)
    if DATABASE_URL else None
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine
)

Base = declarative_base()
