"""Test fixtures for pytest-asyncio with test database."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.db.models import Base


@pytest.fixture(autouse=True)
def _reset_redis_singleton():
    """Drop the process-wide Redis client between tests (B3).

    pytest-asyncio gives every test a fresh event loop; a singleton client
    created in one loop cannot be reused in the next. Prod processes have
    one long-lived loop, so this is a test-only concern.
    """
    yield
    import app.cache
    app.cache._client = None


@pytest_asyncio.fixture(loop_scope="function")
async def session() -> AsyncSession:
    """Provide a transactional session that rolls back after each test."""
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        async with s.begin():
            yield s
            await s.rollback()

    await engine.dispose()
