import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from database import init_db, get_session
from seed import seed_config
from models import FareConfig, FixedPrice, Tool  # noqa: ensure all models imported for create_all
from routes.admin import router as admin_router
from routes.pricing import router as pricing_router
from routes.geocode import router as geocode_router
from routes.config import router as config_router
from routes.tools import router as tools_router
from auth import get_session_secret

load_dotenv()

app = FastAPI(title="Domii Tuluá Fare Calculator")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=get_session_secret(),
    max_age=86400,
)

app.include_router(admin_router)
app.include_router(pricing_router)
app.include_router(geocode_router)
app.include_router(config_router)
app.include_router(tools_router)


@app.on_event("startup")
def startup():
    init_db()
    db = next(get_session())
    try:
        seed_config(db)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import sys
    reload_flag = "--reload" in sys.argv or os.getenv("DEV", "").lower() in ("1", "true")
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=reload_flag)
