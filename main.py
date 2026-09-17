import os
import json
import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from sqlalchemy import text

from database import init_db, AsyncSessionLocal
from seed import seed_config
from models import FareConfig, FixedPrice, Tool, ApiKey  # noqa: ensure all models imported for create_all
from services.cache import cache_stats
from routes.admin import router as admin_router
from routes.pricing import router as pricing_router
from routes.geocode import router as geocode_router, close_http_client
from routes.config import router as config_router
from routes.tools import router as tools_router
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from auth import get_session_secret, refresh_api_key_cache
from rate_limit import rate_limit_provider, rate_limit_key_func, ApiKeyTierMiddleware

load_dotenv()


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    handlers=[_handler],
)
logger = logging.getLogger("domii")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as db:
        try:
            await seed_config(db)
            await refresh_api_key_cache(db)
        except Exception:
            await db.rollback()
            raise
    yield
    await close_http_client()

app = FastAPI(title="Domii Tuluá Fare Calculator", lifespan=lifespan)

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
    same_site="none",
    https_only=True,
)

limiter = Limiter(
    key_func=rate_limit_key_func,
    default_limits=[rate_limit_provider],
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

KNOWN_PREFIXES = ("/api/", "/admin/", "/docs", "/redoc", "/openapi.json")

@app.middleware("http")
async def block_scanner_paths(request: Request, call_next):
    if not request.url.path.startswith(KNOWN_PREFIXES):
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return await call_next(request)

app.add_middleware(SlowAPIMiddleware)
# Added last so it runs outermost and sets the rate-limit tier before slowapi
# evaluates the default limits.
app.add_middleware(ApiKeyTierMiddleware)

app.include_router(admin_router)
app.include_router(pricing_router)
app.include_router(geocode_router)
app.include_router(config_router)
app.include_router(tools_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


@app.get("/api/health")
async def health():
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "error"
        logger.error("Health check DB failure: %s", e)
    return {"status": "ok", "database": db_status, "cache": cache_stats()}


if __name__ == "__main__":
    import sys
    reload_flag = "--reload" in sys.argv or os.getenv("DEV", "").lower() in ("1", "true")
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=reload_flag)
