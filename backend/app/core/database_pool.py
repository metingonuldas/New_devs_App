import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    """Use the asyncpg driver for the configured Postgres URL."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool (only once)."""
        if self.session_factory:
            return
        async with self._lock:
            if self.session_factory:
                return
            try:
                # Settings only define database_url; the old supabase_db_* fields
                # do not exist, so initialization always failed before.
                self.engine = create_async_engine(
                    _async_database_url(settings.database_url),
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_pre_ping=True,
                    pool_recycle=settings.database_pool_recycle,
                    echo=False,
                )

                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )

                logger.info("✅ Database connection pool initialized")

            except Exception as e:
                logger.error(f"❌ Database pool initialization failed: {e}")
                self.engine = None
                self.session_factory = None

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()

    def get_session(self) -> AsyncSession:
        """Get database session from pool (use with `async with`)."""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
