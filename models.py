from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, Text, Boolean, CheckConstraint, DateTime
from database import Base


def utcnow() -> datetime:
    """Naive UTC timestamp.

    SQLAlchemy maps plain ``DateTime`` to PostgreSQL ``TIMESTAMP WITHOUT TIME
    ZONE``; passing a timezone-aware value there is rejected by asyncpg.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FareConfig(Base):
    __tablename__ = "fares_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False, index=True)
    value = Column(Float, nullable=False, default=0.0)
    description = Column(Text, default="")


class FixedPrice(Base):
    __tablename__ = "fixed_prices"

    id = Column(Integer, primary_key=True, index=True)
    service_type = Column(String(50), nullable=True, index=True)
    destination_keyword = Column(String(100), nullable=True, index=True)
    price = Column(Float, nullable=False, default=0.0)
    description = Column(Text, default="")
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    radius_km = Column(Float, nullable=True, default=10.0)

    __table_args__ = (
        CheckConstraint(
            "service_type IS NOT NULL OR destination_keyword IS NOT NULL OR (lat IS NOT NULL AND lng IS NOT NULL)",
            name="ck_fixed_price_has_target",
        ),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="")
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    prefix = Column(String(16), nullable=False, default="")
    privilege = Column(String(10), nullable=False, default="normal")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("privilege IN ('normal', 'admin')", name="ck_api_key_privilege"),
    )


class Tool(Base):
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(30), unique=True, nullable=False, index=True)
    label = Column(String(50), nullable=False)
    description = Column(Text, default="")
    surcharge = Column(Float, nullable=False, default=0.0)
    material_symbol = Column(String(50), nullable=False, default="")
    color = Column(String(7), default="")
    active = Column(Boolean, nullable=False, default=True)
