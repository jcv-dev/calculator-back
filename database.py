import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"

_engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    _engine_kwargs["pool_size"] = 2
    _engine_kwargs["max_overflow"] = 3
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def init_db():
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("tools")]
    if "color" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE tools ADD COLUMN color VARCHAR(7) DEFAULT ''"))
            conn.commit()


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
