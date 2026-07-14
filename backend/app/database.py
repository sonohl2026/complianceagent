from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()


def _to_async_url(url: str) -> str:
    """Normalize a psycopg-style URL to the asyncpg driver used at runtime."""
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_to_async_url(settings.database_url), pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


def create_worker_engine_and_sessionmaker():
    """A fresh engine + sessionmaker for one Celery task invocation.

    Real incident this fixes: each Celery task entrypoint calls
    `asyncio.run(...)`, which creates a brand-new event loop every time.
    asyncpg connections are bound to the event loop they were created on, so
    a connection pooled by the shared `engine` above (used by the long-lived
    FastAPI process, which has exactly one event loop) becomes unusable the
    moment a *different* task's *different* loop tries to check it out --
    asyncpg raises "Future ... attached to a different loop". NullPool means
    nothing is kept between calls, so there is nothing stale to reuse: the
    caller must `await engine.dispose()` when the task finishes.
    """
    worker_engine = create_async_engine(_to_async_url(settings.database_url), poolclass=NullPool)
    worker_sessionmaker = async_sessionmaker(bind=worker_engine, expire_on_commit=False)
    return worker_engine, worker_sessionmaker


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
