import hashlib
import os
import secrets

from fastapi import Request, HTTPException, status, Depends
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import ApiKey

load_dotenv()

API_KEY_PREFIX = "domii_"
API_KEY_BYTES = 32


def get_admin_password():
    pw = os.getenv("ADMIN_PASSWORD")
    if not pw:
        raise RuntimeError("ADMIN_PASSWORD environment variable is not set")
    return pw


def get_session_secret():
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        raise RuntimeError("SESSION_SECRET environment variable is not set")
    return secret


async def login_user(request: Request, password: str) -> bool:
    if password == get_admin_password():
        request.session["admin"] = True
        return True
    return False


async def logout_user(request: Request):
    request.session.pop("admin", None)


# ── API keys ─────────────────────────────────────────────────────────────────


def generate_api_key() -> str:
    """Generate a new raw API key. The raw value is shown to the user once."""
    return API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_BYTES)


def hash_api_key(raw: str) -> str:
    """Hash an API key for storage/lookup. Raw keys are never persisted."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def api_key_prefix(raw: str) -> str:
    return raw[: len(API_KEY_PREFIX) + 8]


def extract_api_key(request: Request) -> str | None:
    """Read the API key from X-API-Key or an Authorization: Bearer header."""
    header_key = request.headers.get("x-api-key")
    if header_key:
        stripped = header_key.strip()
        if stripped:
            return stripped

    authorization = request.headers.get("authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()

    return None


# In-memory cache of valid key hashes -> privilege. Used by the synchronous
# rate-limiter key function and middleware so per-request auth checks don't
# require a database round-trip. Refreshed at startup and kept in sync on
# create/delete.
_api_key_cache: dict[str, str] = {}


def cache_api_key(key_hash: str, privilege: str) -> None:
    _api_key_cache[key_hash] = privilege


def uncache_api_key(key_hash: str) -> None:
    _api_key_cache.pop(key_hash, None)


def clear_api_key_cache() -> None:
    _api_key_cache.clear()


def lookup_cached_api_key(raw: str) -> str | None:
    """Return the privilege of a cached, valid key or None."""
    return _api_key_cache.get(hash_api_key(raw))


async def refresh_api_key_cache(db: AsyncSession) -> None:
    """Reload the in-memory cache from the database."""
    result = await db.execute(select(ApiKey).where(ApiKey.active == True))  # noqa: E712
    rows = result.scalars().all()
    clear_api_key_cache()
    for row in rows:
        cache_api_key(row.key_hash, row.privilege)


async def get_active_api_key(db: AsyncSession, raw: str) -> ApiKey | None:
    """Authoritative lookup used by admin authentication."""
    if not raw:
        return None
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(raw),
            ApiKey.active == True,  # noqa: E712
        )
    )
    return result.scalars().first()


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    if request.session.get("admin"):
        return

    raw = extract_api_key(request)
    if raw:
        record = await get_active_api_key(db, raw)
        if record and record.privilege == "admin":
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )
