import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import NullPool, inspect, text

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, 'database.db')}"

_engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        def _migrate(sync_conn):
            inspector = inspect(sync_conn)
            columns = [c["name"] for c in inspector.get_columns("tools")]
            if "color" not in columns:
                sync_conn.execute(text("ALTER TABLE tools ADD COLUMN color VARCHAR(7) DEFAULT ''"))
        await conn.run_sync(_migrate)
        await conn.commit()


async def get_session():
    async with AsyncSessionLocal() as db:
        yield db
