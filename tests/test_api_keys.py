import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret-api-keys")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.requests import Request

from database import Base, get_session
from main import app
from models import ApiKey
from auth import (
    api_key_prefix,
    cache_api_key,
    clear_api_key_cache,
    extract_api_key,
    generate_api_key,
    hash_api_key,
    lookup_cached_api_key,
)
from rate_limit import (
    API_KEY_RATE_LIMIT,
    RATE_LIMIT,
    rate_limit_key_func,
    resolve_request_rate_limit,
)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSession = async_sessionmaker(bind=engine, autocommit=False, autoflush=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with TestingSession() as session:
            yield session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    async def override_get_session():
        yield db

    app.dependency_overrides.clear()
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_key_cache():
    clear_api_key_cache()
    yield
    clear_api_key_cache()


async def _login(client: AsyncClient, password: str = "keyadminpass") -> None:
    os.environ["ADMIN_PASSWORD"] = password
    resp = await client.post("/admin/api/login", json={"password": password})
    assert resp.status_code == 200


def _request(headers: dict | None = None, client=("1.2.3.4", 1234)) -> Request:
    raw_headers = [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": client,
    }
    return Request(scope)


class TestApiKeyHelpers:
    def test_generate_api_key_is_random(self):
        first = generate_api_key()
        second = generate_api_key()
        assert first.startswith("domii_")
        assert first != second
        assert len(first) > len("domii_") + 20

    def test_hash_is_deterministic_and_not_reversible(self):
        raw = "domii_example"
        assert hash_api_key(raw) == hash_api_key(raw)
        assert hash_api_key(raw) != raw
        assert len(hash_api_key(raw)) == 64

    def test_prefix_matches_key_start(self):
        raw = generate_api_key()
        assert raw.startswith(api_key_prefix(raw))
        assert api_key_prefix(raw).startswith("domii_")

    def test_extract_api_key_header_precedence(self):
        req = _request({"X-API-Key": "from-header", "Authorization": "Bearer from-bearer"})
        assert extract_api_key(req) == "from-header"

    def test_extract_api_key_bearer_fallback(self):
        req = _request({"Authorization": "Bearer from-bearer"})
        assert extract_api_key(req) == "from-bearer"

    def test_extract_api_key_absent(self):
        assert extract_api_key(_request()) is None


class TestApiKeyModel:
    @pytest.mark.asyncio
    async def test_create_api_key(self, db):
        raw = generate_api_key()
        row = ApiKey(
            name="integration",
            key_hash=hash_api_key(raw),
            prefix=api_key_prefix(raw),
            privilege="admin",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        assert row.id is not None
        assert row.privilege == "admin"
        assert row.active is True
        assert row.created_at is not None

    @pytest.mark.asyncio
    async def test_key_hash_is_unique(self, db):
        raw = generate_api_key()
        db.add(ApiKey(key_hash=hash_api_key(raw), prefix=api_key_prefix(raw)))
        await db.commit()

        db.add(ApiKey(key_hash=hash_api_key(raw), prefix=api_key_prefix(raw)))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    @pytest.mark.asyncio
    async def test_privilege_check_constraint(self, db):
        db.add(ApiKey(key_hash=hash_api_key("x"), privilege="superuser"))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


class TestApiKeyAdminCrud:
    @pytest.mark.asyncio
    async def test_create_requires_admin(self, client):
        resp = await client.post("/admin/api/keys", json={"name": "nope"})
        assert resp.status_code == 401

        resp = await client.get("/admin/api/keys")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_returns_raw_key_once_and_stores_hash(self, db, client):
        await _login(client)

        resp = await client.post(
            "/admin/api/keys", json={"name": "Bot", "privilege": "normal"}
        )
        assert resp.status_code == 200
        data = resp.json()

        raw = data["key"]
        assert raw.startswith("domii_")
        assert data["name"] == "Bot"
        assert data["privilege"] == "normal"
        assert data["prefix"] == api_key_prefix(raw)
        assert data["active"] is True

        result = await db.execute(select(ApiKey))
        stored = result.scalars().all()
        assert len(stored) == 1
        assert stored[0].key_hash == hash_api_key(raw)
        assert stored[0].key_hash != raw

    @pytest.mark.asyncio
    async def test_list_never_exposes_secret(self, db, client):
        await _login(client)
        raw = (
            await client.post("/admin/api/keys", json={"name": "Listed"})
        ).json()["key"]

        resp = await client.get("/admin/api/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Listed"
        assert data[0]["prefix"] == api_key_prefix(raw)
        assert data[0]["privilege"] == "normal"
        assert data[0]["active"] is True
        assert data[0]["created_at"]
        assert "key" not in data[0]
        assert "key_hash" not in data[0]

        body = resp.text
        assert raw not in body
        assert hash_api_key(raw) not in body

    @pytest.mark.asyncio
    async def test_delete_removes_key_and_cache(self, db, client):
        await _login(client)
        raw = (
            await client.post("/admin/api/keys", json={"name": "Temp"})
        ).json()["key"]
        assert lookup_cached_api_key(raw) == "normal"

        key_id = (await client.get("/admin/api/keys")).json()[0]["id"]
        resp = await client.delete(f"/admin/api/keys/{key_id}")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True}
        assert lookup_cached_api_key(raw) is None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anon:
            resp = await anon.get("/admin/api/config", headers={"X-API-Key": raw})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_missing_key_returns_404(self, client):
        await _login(client)
        resp = await client.delete("/admin/api/keys/999")
        assert resp.status_code == 404


class TestApiKeyPermissions:
    @pytest.mark.asyncio
    async def test_admin_key_grants_admin_access(self, db, client):
        await _login(client)
        raw = (
            await client.post(
                "/admin/api/keys", json={"name": "Admin", "privilege": "admin"}
            )
        ).json()["key"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anon:
            resp = await anon.get("/admin/api/config", headers={"X-API-Key": raw})
            assert resp.status_code == 200

            resp = await anon.get("/admin/api/check", headers={"X-API-Key": raw})
            assert resp.json() == {"authenticated": True}

    @pytest.mark.asyncio
    async def test_normal_key_is_denied_admin_access(self, db, client):
        await _login(client)
        raw = (
            await client.post(
                "/admin/api/keys", json={"name": "Normal", "privilege": "normal"}
            )
        ).json()["key"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anon:
            resp = await anon.get("/admin/api/config", headers={"X-API-Key": raw})
            assert resp.status_code == 401

            resp = await anon.get("/admin/api/check", headers={"X-API-Key": raw})
            assert resp.json() == {"authenticated": False}

    @pytest.mark.asyncio
    async def test_key_accepted_via_bearer_header(self, db, client):
        await _login(client)
        raw = (
            await client.post(
                "/admin/api/keys", json={"name": "Bearer", "privilege": "admin"}
            )
        ).json()["key"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anon:
            resp = await anon.get(
                "/admin/api/config",
                headers={"Authorization": f"Bearer {raw}"},
            )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_key_is_denied(self, client):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anon:
            resp = await anon.get(
                "/admin/api/config", headers={"X-API-Key": "domii_not-a-real-key"}
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_normal_key_can_use_public_api(self, db, client):
        await _login(client)
        raw = (
            await client.post(
                "/admin/api/keys", json={"name": "Public", "privilege": "normal"}
            )
        ).json()["key"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as anon:
            resp = await anon.get("/api/tools", headers={"X-API-Key": raw})
        assert resp.status_code == 200


class TestApiKeyRateLimitTiers:
    def test_valid_key_gets_higher_limit(self):
        raw = generate_api_key()
        cache_api_key(hash_api_key(raw), "normal")

        req = _request({"X-API-Key": raw})
        assert rate_limit_key_func(req) == f"apikey:{hash_api_key(raw)}"
        assert resolve_request_rate_limit(req) == API_KEY_RATE_LIMIT
        assert API_KEY_RATE_LIMIT != RATE_LIMIT

    def test_valid_key_via_bearer_gets_higher_limit(self):
        raw = generate_api_key()
        cache_api_key(hash_api_key(raw), "admin")

        req = _request({"Authorization": f"Bearer {raw}"})
        assert rate_limit_key_func(req) == f"apikey:{hash_api_key(raw)}"
        assert resolve_request_rate_limit(req) == API_KEY_RATE_LIMIT

    def test_invalid_key_falls_back_to_ip(self):
        req = _request({"X-API-Key": generate_api_key()})
        assert rate_limit_key_func(req) == "1.2.3.4"
        assert resolve_request_rate_limit(req) == RATE_LIMIT

    def test_anonymous_falls_back_to_ip(self):
        req = _request()
        assert rate_limit_key_func(req) == "1.2.3.4"
        assert resolve_request_rate_limit(req) == RATE_LIMIT
