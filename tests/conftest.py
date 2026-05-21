import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_session
from main import app
from models import FareConfig, FixedPrice, Tool
from seed import DEFAULT_CONFIG, DEFAULT_FIXED_PRICES, DEFAULT_TOOLS


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()
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
            active=tool["active"],
        ))
    session.commit()

    yield session
    session.close()


@pytest.fixture
def config_rows(db):
    return db.query(FareConfig).all()


@pytest.fixture
def tool_rows(db):
    return db.query(Tool).all()


@pytest.fixture
def overrides():
    import os
    os.environ["OPENWEATHER_API_KEY"] = ""
    os.environ["WHATSAPP_NUMBER"] = "573001234567"
    yield
