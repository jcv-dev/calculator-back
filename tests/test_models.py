import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import FareConfig, FixedPrice


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    s = TestingSession()
    yield s
    s.close()


class TestFareConfig:
    def test_create(self, session):
        fc = FareConfig(key="TEST_KEY", value=1000.0, description="Test")
        session.add(fc)
        session.commit()
        assert fc.id is not None
        assert fc.key == "TEST_KEY"

    def test_unique_key_constraint(self, session):
        session.add(FareConfig(key="DUP", value=1.0))
        session.commit()
        session.add(FareConfig(key="DUP", value=2.0))
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


class TestFixedPrice:
    def test_create_with_service_type(self, session):
        fp = FixedPrice(service_type="purchases", price=8000.0)
        session.add(fp)
        session.commit()
        assert fp.id is not None

    def test_create_with_keyword(self, session):
        fp = FixedPrice(destination_keyword="cali", price=120000.0)
        session.add(fp)
        session.commit()
        assert fp.id is not None

    def test_create_with_both(self, session):
        fp = FixedPrice(
            service_type="domicilios",
            destination_keyword="cali",
            price=150000.0,
        )
        session.add(fp)
        session.commit()
        assert fp.id is not None


class TestTool:
    def test_create_with_color(self, session):
        from models import Tool
        t = Tool(key="test_tool", label="Test", material_symbol="star", color="#ff6600")
        session.add(t)
        session.commit()
        assert t.id is not None
        assert t.color == "#ff6600"

    def test_color_defaults_to_empty(self, session):
        from models import Tool
        t = Tool(key="no_color", label="No Color", material_symbol="circle")
        session.add(t)
        session.commit()
        assert t.color == ""
