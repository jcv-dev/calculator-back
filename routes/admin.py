from datetime import timezone
from typing import Literal

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_session
from models import FareConfig, FixedPrice, Tool, ApiKey
from auth import (
    login_user,
    logout_user,
    require_admin,
    extract_api_key,
    get_active_api_key,
    generate_api_key,
    hash_api_key,
    api_key_prefix,
    cache_api_key,
    uncache_api_key,
)

router = APIRouter(prefix="/admin/api")


class LoginRequest(BaseModel):
    password: str


class UpdateConfigRequest(BaseModel):
    value: float


class CreateConfigRequest(BaseModel):
    key: str
    value: float
    description: str = ""


class FixedPriceCreate(BaseModel):
    service_type: str | None = None
    destination_keyword: str | None = None
    price: float
    description: str = ""
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None


class FixedPriceUpdate(BaseModel):
    service_type: str | None = None
    destination_keyword: str | None = None
    price: float | None = None
    description: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None


class ToolCreate(BaseModel):
    key: str
    label: str
    description: str = ""
    surcharge: float = 0.0
    material_symbol: str
    color: str = ""
    active: bool = True


class ToolUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    surcharge: float | None = None
    material_symbol: str | None = None
    color: str | None = None
    active: bool | None = None


class ApiKeyCreate(BaseModel):
    name: str = ""
    privilege: Literal["normal", "admin"] = "normal"


def _iso_utc(value):
    """Serialize a stored naive-UTC datetime with an explicit UTC offset."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _serialize_api_key(row: ApiKey) -> dict:
    """Never expose the raw key or its hash — only the display prefix."""
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "privilege": row.privilege,
        "active": row.active,
        "created_at": _iso_utc(row.created_at),
    }


@router.post("/login")
async def admin_login(request: Request, body: LoginRequest):
    ok = await login_user(request, body.password)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"authenticated": True}


@router.get("/check")
async def admin_check(request: Request, db: AsyncSession = Depends(get_session)):
    if request.session.get("admin"):
        return {"authenticated": True}

    raw = extract_api_key(request)
    if raw:
        record = await get_active_api_key(db, raw)
        if record and record.privilege == "admin":
            return {"authenticated": True}

    return {"authenticated": False}


@router.post("/logout")
async def admin_logout(request: Request):
    await logout_user(request)
    return {"authenticated": False}


@router.get("/config")
async def list_config(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FareConfig).order_by(FareConfig.key))
    rows = result.scalars().all()
    return [
        {
            "key": r.key,
            "value": r.value,
            "description": r.description,
        }
        for r in rows
    ]


@router.post("/config")
async def create_config(
    request: Request,
    body: CreateConfigRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FareConfig).where(FareConfig.key == body.key))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Config key already exists")
    row = FareConfig(key=body.key, value=float(body.value), description=body.description)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"key": row.key, "value": row.value, "description": row.description}


@router.put("/config/{key}")
async def update_config(
    request: Request,
    key: str,
    body: UpdateConfigRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FareConfig).where(FareConfig.key == key))
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Config key not found")
    row.value = body.value
    await db.commit()
    return {"key": row.key, "value": row.value, "description": row.description}


@router.delete("/config/{key}")
async def delete_config(
    request: Request,
    key: str,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FareConfig).where(FareConfig.key == key))
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Config key not found")
    await db.delete(row)
    await db.commit()
    return {"deleted": True}


@router.get("/fixed-prices")
async def list_fixed_prices(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FixedPrice).order_by(FixedPrice.id))
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "service_type": r.service_type,
            "destination_keyword": r.destination_keyword,
            "price": r.price,
            "description": r.description,
            "lat": r.lat,
            "lng": r.lng,
            "radius_km": r.radius_km,
        }
        for r in rows
    ]


@router.post("/fixed-prices")
async def create_fixed_price(
    request: Request,
    body: FixedPriceCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    if not body.service_type and not body.destination_keyword and not (body.lat and body.lng):
        raise HTTPException(
            status_code=400,
            detail="Either service_type, destination_keyword, or lat+lng must be provided",
        )
    fp = FixedPrice(
        service_type=body.service_type,
        destination_keyword=body.destination_keyword,
        price=body.price,
        description=body.description,
        lat=body.lat,
        lng=body.lng,
        radius_km=body.radius_km,
    )
    db.add(fp)
    await db.commit()
    await db.refresh(fp)
    return {
        "id": fp.id,
        "service_type": fp.service_type,
        "destination_keyword": fp.destination_keyword,
        "price": fp.price,
        "description": fp.description,
        "lat": fp.lat,
        "lng": fp.lng,
        "radius_km": fp.radius_km,
    }


@router.put("/fixed-prices/{fp_id}")
async def update_fixed_price(
    request: Request,
    fp_id: int,
    body: FixedPriceUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FixedPrice).where(FixedPrice.id == fp_id))
    fp = result.scalars().first()
    if not fp:
        raise HTTPException(status_code=404, detail="Fixed price not found")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fp, field, value)
    await db.commit()
    await db.refresh(fp)
    return {
        "id": fp.id,
        "service_type": fp.service_type,
        "destination_keyword": fp.destination_keyword,
        "price": fp.price,
        "description": fp.description,
        "lat": fp.lat,
        "lng": fp.lng,
        "radius_km": fp.radius_km,
    }


@router.delete("/fixed-prices/{fp_id}")
async def delete_fixed_price(
    request: Request,
    fp_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(FixedPrice).where(FixedPrice.id == fp_id))
    fp = result.scalars().first()
    if not fp:
        raise HTTPException(status_code=404, detail="Fixed price not found")
    await db.delete(fp)
    await db.commit()
    return {"deleted": True}


@router.get("/tools")
async def list_tools(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(Tool).order_by(Tool.key))
    rows = result.scalars().all()
    return [
        {
            "id": t.id,
            "key": t.key,
            "label": t.label,
            "description": t.description,
            "surcharge": t.surcharge,
            "material_symbol": t.material_symbol,
            "color": t.color or "",
            "active": t.active,
        }
        for t in rows
    ]


@router.post("/tools")
async def create_tool(
    request: Request,
    body: ToolCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(Tool).where(Tool.key == body.key))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Tool key already exists")
    tool = Tool(
        key=body.key,
        label=body.label,
        description=body.description,
        surcharge=body.surcharge,
        material_symbol=body.material_symbol,
        color=body.color,
        active=body.active,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return {
        "id": tool.id,
        "key": tool.key,
        "label": tool.label,
        "description": tool.description,
        "surcharge": tool.surcharge,
        "material_symbol": tool.material_symbol,
        "color": tool.color or "",
        "active": tool.active,
    }


@router.put("/tools/{tool_id}")
async def update_tool(
    request: Request,
    tool_id: int,
    body: ToolUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalars().first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    if body.label is not None:
        tool.label = body.label
    if body.description is not None:
        tool.description = body.description
    if body.surcharge is not None:
        tool.surcharge = body.surcharge
    if body.material_symbol is not None:
        tool.material_symbol = body.material_symbol
    if body.color is not None:
        tool.color = body.color
    if body.active is not None:
        tool.active = body.active
    await db.commit()
    await db.refresh(tool)
    return {
        "id": tool.id,
        "key": tool.key,
        "label": tool.label,
        "description": tool.description,
        "surcharge": tool.surcharge,
        "material_symbol": tool.material_symbol,
        "color": tool.color or "",
        "active": tool.active,
    }


@router.delete("/tools/{tool_id}")
async def delete_tool(
    request: Request,
    tool_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalars().first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    await db.delete(tool)
    await db.commit()
    return {"deleted": True}


@router.get("/keys")
async def list_api_keys(
    request: Request,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(ApiKey).order_by(ApiKey.id.desc()))
    return [_serialize_api_key(row) for row in result.scalars().all()]


@router.post("/keys")
async def create_api_key(
    request: Request,
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    raw_key = generate_api_key()
    row = ApiKey(
        name=body.name,
        key_hash=hash_api_key(raw_key),
        prefix=api_key_prefix(raw_key),
        privilege=body.privilege,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    cache_api_key(row.key_hash, row.privilege)

    # The raw key is returned exactly once, at creation time.
    return {**_serialize_api_key(row), "key": raw_key}


@router.delete("/keys/{key_id}")
async def delete_api_key(
    request: Request,
    key_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(require_admin),
):
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="API key not found")
    key_hash = row.key_hash
    await db.delete(row)
    await db.commit()
    uncache_api_key(key_hash)
    return {"deleted": True}
