import os
from contextvars import ContextVar

from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.util import get_remote_address

from auth import extract_api_key, hash_api_key, lookup_cached_api_key

load_dotenv()

# Anonymous / IP-based limit.
RATE_LIMIT = os.getenv("RATE_LIMIT", "30/minute")

# Higher limit granted to requests bearing a valid API key.
API_KEY_RATE_LIMIT = os.getenv("API_KEY_RATE_LIMIT", "120/minute")

# Per-request rate limit tier, set by ApiKeyTierMiddleware before slowapi
# evaluates the default limits. ContextVars are inherited by the request task,
# so the value is visible to SlowAPIMiddleware further down the stack.
_current_limit: ContextVar[str] = ContextVar("current_rate_limit", default=RATE_LIMIT)


def rate_limit_provider() -> str:
    """Zero-argument callable used as slowapi's dynamic default limit."""
    return _current_limit.get()


def rate_limit_key_func(request) -> str:
    """Bucket valid API keys separately from anonymous IPs."""
    raw = extract_api_key(request)
    if raw and lookup_cached_api_key(raw) is not None:
        return f"apikey:{hash_api_key(raw)}"
    return get_remote_address(request)


def resolve_request_rate_limit(request) -> str:
    """Return the limit string that applies to this request."""
    raw = extract_api_key(request)
    if raw and lookup_cached_api_key(raw) is not None:
        return API_KEY_RATE_LIMIT
    return RATE_LIMIT


class ApiKeyTierMiddleware(BaseHTTPMiddleware):
    """Select the rate-limit tier for each request based on its API key."""

    async def dispatch(self, request, call_next):
        _current_limit.set(resolve_request_rate_limit(request))
        return await call_next(request)
