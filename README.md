# Domii Tuluá — Backend (FastAPI)

Fare calculation engine for Domii Tuluá. Exposes a REST API for computing delivery prices based on distance, tools, payment method, weather, and an admin panel for configuration.

## Tech Stack

- **FastAPI** (ASGI framework)
- **SQLAlchemy** + **SQLite** (ORM / database)
- **Uvicorn** (ASGI server)
- **httpx** (async HTTP client for external APIs)
- **python-dotenv** (environment variable loader)
- **itsdangerous** (session cookie signing via Starlette's `SessionMiddleware`)
- **slowapi** (IP-based rate limiting, 30 req/min default)

## External API Dependencies

| API | Purpose | Key Required |
|-----|---------|-------------|
| [Nominatim](https://nominatim.openstreetmap.org/) (OSM) | Geocode addresses → lat/lng | No (free, rate-limited) |
| [OSRM](http://project-osrm.org/) | Driving distance for multi-stop routes | No (free, rate-limited) |
| [OpenWeatherMap](https://openweathermap.org/) | Rain detection for Tuluá | Yes (free tier, API key required) |

## Project Structure

```
backend/
├── .env.example           # Required env vars template
├── main.py                # FastAPI app entry point
├── database.py            # SQLAlchemy engine, session, Base
├── models.py              # FareConfig + FixedPrice ORM models
├── seed.py                # Default config + fixed_prices seeder
├── auth.py                # Admin auth (password + session)
├── routes/
│   ├── admin.py           # Admin: login, config CRUD, fixed_prices CRUD
│   ├── pricing.py         # Segment-based fare calculation
│   ├── geocode.py         # Nominatim autocomplete proxy
│   └── config.py          # Public config (WhatsApp number)
├── services/
│   ├── constants.py       # Service type definitions
│   ├── fixed_prices.py    # Keyword + service-type price lookup
│   ├── geocode.py         # Nominatim geocoding
│   ├── osrm.py            # OSRM distance calculation
│   ├── weather.py         # OpenWeather rain check
│   └── pricing_engine.py  # Segment-aware business logic
├── tests/
│   ├── conftest.py
│   ├── test_pricing_engine.py
│   ├── test_fixed_prices.py
│   ├── test_api.py
│   └── test_models.py
└── requirements.txt
```

## Security

### Scanner Path Blocking

Requests to non-API paths (`/.env`, `/Dockerfile`, `/.git/config`, etc.) are rejected at the middleware level with a fast `404` response — before reaching any route handler.

### Rate Limiting

All endpoints are rate-limited per IP via `slowapi` (default: 30 requests/minute). Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT` | `30/minute` | Anonymous/IP rate limit string (see [limits](https://limits.readthedocs.io/) format) |
| `API_KEY_RATE_LIMIT` | `120/minute` | Higher limit applied to requests with a valid API key |
| `RATE_LIMIT_ENABLED` | `true` | Set to `false` to disable rate limiting entirely |

When the limit is exceeded, the API returns `429 Too Many Requests`.

### API Keys

API keys let integrations call the API without a browser session and with a higher rate limit. Each key has one of two privileges:

| Privilege | Access |
|-----------|--------|
| `normal` | Same as an anonymous caller (public `/api/*` routes) + higher rate limit |
| `admin` | Everything a normal key can do, **plus** full access to `/admin/api/*` |

- Send the key in the `X-API-Key` header, or as `Authorization: Bearer <key>`.
- Keys are generated as `domii_<random>` and stored only as a SHA-256 hash — the raw key is returned **once**, at creation time.
- Manage keys from the admin panel (**API Keys** tab) or via the admin API below.
- Valid keys are cached in memory at startup and kept in sync on create/delete (single-process deployments).

## API Endpoints

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/calculate-price` | Segment-based fare calculation |
| `GET` | `/api/geocode/search?q=...` | Address autocomplete (Nominatim proxy, bounded to Valle del Cauca) |
| `GET` | `/api/config/whatsapp` | Read WhatsApp number |

### Admin (session-auth protected)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/api/login` | Login with password |
| `GET` | `/admin/api/check` | Check auth status |
| `POST` | `/admin/api/logout` | Logout |
| `GET` | `/admin/api/config` | List all fare config entries |
| `PUT` | `/admin/api/config/{key}` | Update a config value |
| `GET` | `/admin/api/fixed-prices` | List all fixed prices |
| `POST` | `/admin/api/fixed-prices` | Create a fixed price |
| `PUT` | `/admin/api/fixed-prices/{id}` | Update a fixed price |
| `DELETE` | `/admin/api/fixed-prices/{id}` | Delete a fixed price |
| `GET` | `/admin/api/keys` | List API keys (metadata only) |
| `POST` | `/admin/api/keys` | Create an API key (returns the raw key once) |
| `DELETE` | `/admin/api/keys/{id}` | Delete an API key |

All admin endpoints also accept an API key with `admin` privilege (via `X-API-Key` or `Authorization: Bearer`).

## Database Schema

### `fares_config` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Auto-increment |
| `key` | String(50), UNIQUE | Config key name |
| `value` | Float | Config value |
| `description` | Text | Human-readable description |

### Default Config Keys

| Key | Default | Description |
|-----|---------|-------------|
| `BASE_FARE` | 3500 | Minimum fare up to 1.0 km |
| `EXTRA_STOP_FEE` | 1500 | Per additional stop beyond first distance-based segment |
| `TOOL_CANASTA` | 1000 | Heavy/bulky food surcharge |
| `TOOL_MALETIN` | 500 | Thermal backpack surcharge |
| `METODO_NEQUI_SURCHARGE` | 500 | Nequi/Daviplata handling fee |
| `RAIN_SURCHARGE` | 1000 | Dynamic rain surcharge |

### `fixed_prices` table (full-price overrides)

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Auto-increment |
| `service_type` | String(50), nullable | Target a specific service (e.g. `purchases`) |
| `destination_keyword` | String(100), nullable | Case-insensitive keyword match in address |
| `price` | Float | Full override price (no modifiers applied) |
| `description` | Text | Human-readable |

At least one of `service_type`/`destination_keyword` must be non-null. When a keyword matches any segment's address, the entire request is priced at that fixed price (bypasses distance calc and all modifiers). When a service_type matches a segment with no coords, only that segment is priced at the fixed price.

### `api_keys` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Auto-increment |
| `name` | String(100) | Human-readable label |
| `key_hash` | String(64), UNIQUE | SHA-256 hash of the raw key (raw key is never stored) |
| `prefix` | String(16) | First characters of the key, shown in the admin list |
| `privilege` | String(10) | `normal` or `admin` |
| `active` | Boolean | Inactive keys are rejected |
| `created_at` | DateTime | Creation timestamp (UTC) |

## Calculation Logic

**Distance pricing tiers** (hardcoded):

| Range | Rate |
|-------|------|
| 0–1.0 km | `BASE_FARE` (flat) |
| 1.0–3.0 km | +1000 COP/km |
| 3.0–5.0 km | +800 COP/km |
| 5.0+ km | +700 COP/km |

Route cost is rounded to the nearest 100 COP.

## Development

### Prerequisites

- Python 3.12+
- `venv` module

### Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Description |
|----------|-------------|
| `OPENWEATHER_API_KEY` | Free key from https://openweathermap.org/ |
| `ADMIN_PASSWORD` | Password for the admin panel |
| `SESSION_SECRET` | Random string for cookie signing (e.g. `openssl rand -hex 32`) |
| `RATE_LIMIT` | Anonymous/IP rate limit string (default: `30/minute`) |
| `API_KEY_RATE_LIMIT` | Rate limit for valid API keys (default: `120/minute`) |
| `RATE_LIMIT_ENABLED` | Set to `false` to disable rate limiting |

### Run

```bash
python main.py
```

Server starts at `http://localhost:8000` with auto-reload enabled.

### Database

SQLite file (`database.db`) is created automatically in the `backend/` directory on first run. The config table is seeded with defaults on every startup (existing rows are preserved).

## Production

### Prerequisites

- Python 3.12+
- Production-grade ASGI server (Uvicorn with Gunicorn, or Daphne)
- Reverse proxy (nginx, Caddy, Traefik)
- Process manager (systemd, supervisor) or container runtime (Docker)

### Tests

```bash
cd backend
source venv/bin/activate
python -m pytest tests/ -v
```

### Environment Variables

Set these in the production environment (not `.env` — use the platform's secrets management):

```bash
export OPENWEATHER_API_KEY=your_key
export ADMIN_PASSWORD=secure_password
export SESSION_SECRET=$(openssl rand -hex 32)
export WHATSAPP_NUMBER=57300XXXXXXX
export RATE_LIMIT=30/minute
export API_KEY_RATE_LIMIT=120/minute
export RATE_LIMIT_ENABLED=true
```

### CORS Configuration

Before deploying, update `allow_origins` in `main.py` to include your production domain:

```python
allow_origins=[
    "https://your-production-domain.com",
    "https://www.your-production-domain.com",
],
```

### Running

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
```

> **Note:** SQLite does not support concurrent writes from multiple workers. For multi-worker deployments, migrate to PostgreSQL:
> 1. Install `psycopg2-binary` or `asyncpg`
> 2. Change `DATABASE_URL` in `database.py` to a PostgreSQL connection string
> 3. SQLite-specific `connect_args={"check_same_thread": False}` can be removed

### Example nginx Config

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Docker (suggested `Dockerfile`)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

> No Dockerfile is included in the repo yet — create one from the template above.
