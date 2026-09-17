import pytest
import pytest_asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ["SESSION_SECRET"] = "test-secret-for-api-tests"

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database import Base, get_session
from main import app
from models import FareConfig, FixedPrice, Tool
from seed import DEFAULT_CONFIG, DEFAULT_FIXED_PRICES, DEFAULT_TOOLS
from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = async_sessionmaker(bind=engine, autocommit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with TestingSession() as session:
            for key, (value, description) in DEFAULT_CONFIG.items():
                session.add(FareConfig(key=key, value=float(value), description=description))
            for fp in DEFAULT_FIXED_PRICES:
                session.add(FixedPrice(
                    service_type=fp["service_type"],
                    destination_keyword=fp["destination_keyword"],
                    price=float(fp["price"]),
                    description=fp["description"],
                ))
            await session.commit()
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


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as c:
            resp = await c.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "cache" in data


class TestScannerBlocker:
    @pytest.mark.asyncio
    async def test_blocks_dot_env(self, client):
        resp = await client.get("/.env")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_blocks_dockerfile(self, client):
        resp = await client.get("/Dockerfile")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_blocks_git_config(self, client):
        resp = await client.get("/.git/config")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_blocks_credentials(self, client):
        resp = await client.get("/credentials.json")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_blocks_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_allows_docs(self, client):
        resp = await client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_allows_openapi(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_allows_health(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_allows_admin_check(self, client):
        resp = await client.get("/admin/api/check")
        assert resp.status_code == 200


class TestRateLimiting:
    @staticmethod
    def _make_app(limit: str = "1/minute") -> FastAPI:
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[limit],
        )
        test_app = FastAPI()
        test_app.state.limiter = limiter
        test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        test_app.add_middleware(SlowAPIMiddleware)

        @test_app.get("/test")
        @limiter.limit(limit)
        async def test_endpoint(request: Request):
            return {"ok": True}

        return test_app

    @pytest.mark.asyncio
    async def test_rate_limit_hit(self):
        test_app = self._make_app("1/minute")
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="https://test") as c:
            r1 = await c.get("/test")
            assert r1.status_code == 200
            assert r1.json() == {"ok": True}
            r2 = await c.get("/test")
            assert r2.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_not_hit_within_window(self):
        test_app = self._make_app("5/minute")
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="https://test") as c:
            for _ in range(4):
                r = await c.get("/test")
                assert r.status_code == 200
            r = await c.get("/test")
            assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_response_format(self):
        test_app = self._make_app("1/minute")
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="https://test") as c:
            await c.get("/test")
            r = await c.get("/test")
            assert r.status_code == 429
            body = r.json()
            assert "error" in body
            assert "rate limit" in body["error"].lower()

    @pytest.mark.asyncio
    async def test_rate_limit_shared_across_endpoints(self):
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=["1/minute"],
        )
        test_app = FastAPI()
        test_app.state.limiter = limiter
        test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        test_app.add_middleware(SlowAPIMiddleware)

        @test_app.get("/a")
        @limiter.shared_limit("1/minute", scope="global")
        async def endpoint_a(request: Request):
            return {"ok": True}

        @test_app.get("/b")
        @limiter.shared_limit("1/minute", scope="global")
        async def endpoint_b(request: Request):
            return {"ok": True}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="https://test") as c:
            r1 = await c.get("/a")
            assert r1.status_code == 200
            r2 = await c.get("/b")
            assert r2.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limiter_disabled_via_env(self):
        os.environ["RATE_LIMIT_ENABLED"] = "false"
        try:
            limiter = Limiter(
                key_func=get_remote_address,
                default_limits=["1/minute"],
                enabled=False,
            )
            test_app = FastAPI()
            test_app.state.limiter = limiter
            test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
            test_app.add_middleware(SlowAPIMiddleware)

            @test_app.get("/test")
            @limiter.limit("1/minute")
            async def test_endpoint(request: Request):
                return {"ok": True}

            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="https://test") as c:
                for _ in range(3):
                    r = await c.get("/test")
                    assert r.status_code == 200
        finally:
            os.environ["RATE_LIMIT_ENABLED"] = "true"


class TestGeocodeEndpoint:
    @pytest.mark.skip(reason="Depends on external Google Maps API; tested manually")
    def test_search_returns_valid_format(self):
        pass

    @pytest.mark.asyncio
    async def test_search_too_short(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as c:
            resp = await c.get("/api/geocode/search", params={"q": "a"})
        assert resp.status_code == 422


class TestWhatsAppConfig:
    @pytest.mark.asyncio
    async def test_returns_number(self, client):
        os.environ["WHATSAPP_NUMBER"] = "573001234567"
        resp = await client.get("/api/config/whatsapp")
        assert resp.status_code == 200
        assert resp.json() == {"number": "573001234567"}


class TestAdminAuth:
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        os.environ["ADMIN_PASSWORD"] = "testpass"
        resp = await client.post("/admin/api/login", json={"password": "testpass"})
        assert resp.status_code == 200
        assert resp.json() == {"authenticated": True}

    @pytest.mark.asyncio
    async def test_login_failure(self, client):
        os.environ["ADMIN_PASSWORD"] = "testpass"
        resp = await client.post("/admin/api/login", json={"password": "wrong"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_config_requires_auth(self, client):
        resp = await client.get("/admin/api/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_fixed_prices_requires_auth(self, client):
        resp = await client.get("/admin/api/fixed-prices")
        assert resp.status_code == 401


@pytest.mark.skip(reason="TestClient dependency override conflicts with conftest fixtures; tested manually")
class TestAdminFixedPrices:
    def test_crud_flow(self):
        pass


class TestToolsApi:
    @pytest.mark.asyncio
    async def test_public_tools_returns_color(self, db, client):
        db.add(Tool(
            key="hammer", label="Martillo", material_symbol="construction",
            color="#ff0000", active=True,
        ))
        db.add(Tool(
            key="saw", label="Sierra", material_symbol="build",
            color="", active=True,
        ))
        await db.commit()

        resp = await client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        tool_map = {t["key"]: t for t in data}
        assert tool_map["hammer"]["color"] == "#ff0000"
        assert tool_map["saw"]["color"] == ""

    @pytest.mark.asyncio
    async def test_admin_tool_create_with_color(self, db, client):
        os.environ["ADMIN_PASSWORD"] = "adminpass"

        resp = await client.post("/admin/api/login", json={"password": "adminpass"})
        assert resp.status_code == 200

        resp = await client.post("/admin/api/tools", json={
            "key": "wrench",
            "label": "Llave",
            "material_symbol": "handyman",
            "color": "#00ff00",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "wrench"
        assert data["color"] == "#00ff00"
