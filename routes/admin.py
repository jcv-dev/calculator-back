from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_session
from models import FareConfig, FixedPrice, Tool
from auth import login_user, logout_user, require_admin

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
    active: bool = True


class ToolUpdate(BaseModel):
    label: str | None = None
    description: str | None = None
    surcharge: float | None = None
    material_symbol: str | None = None
    active: bool | None = None


@router.post("/login")
async def admin_login(request: Request, body: LoginRequest):
    ok = await login_user(request, body.password)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"authenticated": True}


@router.get("/check")
async def admin_check(request: Request):
    return {"authenticated": request.session.get("admin", False)}


@router.post("/logout")
async def admin_logout(request: Request):
    await logout_user(request)
    return {"authenticated": False}


@router.get("/config")
async def list_config(
    request: Request,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    rows = db.query(FareConfig).order_by(FareConfig.key).all()
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
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    existing = db.query(FareConfig).filter(FareConfig.key == body.key).first()
    if existing:
        raise HTTPException(status_code=400, detail="Config key already exists")
    row = FareConfig(key=body.key, value=float(body.value), description=body.description)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"key": row.key, "value": row.value, "description": row.description}


@router.put("/config/{key}")
async def update_config(
    request: Request,
    key: str,
    body: UpdateConfigRequest,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    row = db.query(FareConfig).filter(FareConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Config key not found")
    row.value = body.value
    db.commit()
    return {"key": row.key, "value": row.value, "description": row.description}


@router.delete("/config/{key}")
async def delete_config(
    request: Request,
    key: str,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    row = db.query(FareConfig).filter(FareConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Config key not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.get("/fixed-prices")
async def list_fixed_prices(
    request: Request,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    rows = db.query(FixedPrice).order_by(FixedPrice.id).all()
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
    db: Session = Depends(get_session),
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
    db.commit()
    db.refresh(fp)
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
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    fp = db.query(FixedPrice).filter(FixedPrice.id == fp_id).first()
    if not fp:
        raise HTTPException(status_code=404, detail="Fixed price not found")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fp, field, value)
    db.commit()
    db.refresh(fp)
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
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    fp = db.query(FixedPrice).filter(FixedPrice.id == fp_id).first()
    if not fp:
        raise HTTPException(status_code=404, detail="Fixed price not found")
    db.delete(fp)
    db.commit()
    return {"deleted": True}


@router.get("/tools")
async def list_tools(
    request: Request,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    rows = db.query(Tool).order_by(Tool.key).all()
    return [
        {
            "id": t.id,
            "key": t.key,
            "label": t.label,
            "description": t.description,
            "surcharge": t.surcharge,
            "material_symbol": t.material_symbol,
            "active": t.active,
        }
        for t in rows
    ]


@router.post("/tools")
async def create_tool(
    request: Request,
    body: ToolCreate,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    existing = db.query(Tool).filter(Tool.key == body.key).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tool key already exists")
    tool = Tool(
        key=body.key,
        label=body.label,
        description=body.description,
        surcharge=body.surcharge,
        material_symbol=body.material_symbol,
        active=body.active,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return {
        "id": tool.id,
        "key": tool.key,
        "label": tool.label,
        "description": tool.description,
        "surcharge": tool.surcharge,
        "material_symbol": tool.material_symbol,
        "active": tool.active,
    }


@router.put("/tools/{tool_id}")
async def update_tool(
    request: Request,
    tool_id: int,
    body: ToolUpdate,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
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
    if body.active is not None:
        tool.active = body.active
    db.commit()
    db.refresh(tool)
    return {
        "id": tool.id,
        "key": tool.key,
        "label": tool.label,
        "description": tool.description,
        "surcharge": tool.surcharge,
        "material_symbol": tool.material_symbol,
        "active": tool.active,
    }


@router.delete("/tools/{tool_id}")
async def delete_tool(
    request: Request,
    tool_id: int,
    db: Session = Depends(get_session),
    _=Depends(require_admin),
):
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    db.delete(tool)
    db.commit()
    return {"deleted": True}
