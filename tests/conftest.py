import os
os.environ.setdefault("SESSION_SECRET", "conftest-secret")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from database import Base, get_session
from main import app
from models import FareConfig, FixedPrice, Tool
from seed import DEFAULT_CONFIG, DEFAULT_FIXED_PRICES, DEFAULT_TOOLS


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = async_sessionmaker(bind=engine, autocommit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSession() as session:
        for key, (value, description) in DEFAULT_CONFIG.items():
            session.add(FareConfig(key=key, value=float(value), description=description))
        for fp in DEFAULT_FIXED_PRICES:
            session.add(FixedPrice(
                service_type=fp["service_type"],
                destination_keyword=fp["destination_keyword"],
                price=float(fp["price"]),
                description=fp["description"],
                lat=fp.get("lat"),
                lng=fp.get("lng"),
                radius_km=fp.get("radius_km"),
            ))
        for tool in DEFAULT_TOOLS:
            session.add(Tool(
                key=tool["key"],
                label=tool["label"],
                description=tool["description"],
                surcharge=float(tool["surcharge"]),
                material_symbol=tool["material_symbol"],
                color=tool.get("color", ""),
                active=tool["active"],
            ))
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def config_rows(db):
    result = await db.execute(select(FareConfig))
    return result.scalars().all()


@pytest_asyncio.fixture
async def tool_rows(db):
    result = await db.execute(select(Tool))
    return result.scalars().all()


@pytest.fixture
def overrides():
    import os
    os.environ["OPENWEATHER_API_KEY"] = ""
    os.environ["WHATSAPP_NUMBER"] = "573001234567"
    yield
