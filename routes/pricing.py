from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_session
from models import FareConfig, Tool
from services.geocode import geocode_address
from services.osrm import get_total_distance
from services.weather import check_rain
from services.pricing_engine import calculate_full_price
from services.fixed_prices import find_keyword_match, find_proximity_match, get_service_price
from services.constants import SERVICE_TYPES

router = APIRouter(prefix="/api")


class LocationItem(BaseModel):
    address: str
    lat: float | None = None
    lng: float | None = None


class SegmentItem(BaseModel):
    service_type: str
    description: str = ""
    origin: LocationItem | None = None
    destination: LocationItem
    instructions: str | None = None


class PriceRequest(BaseModel):
    profile: str = "usuario_final"
    segments: list[SegmentItem]
    tools: list[str] = []
    payment_method: str = "efectivo"
    acompanante: bool = False


TULUA_CENTRO = (4.0847, -76.1954)
DISTANCE_SERVICE_TYPES = {"domicilios", "mensajeria", "tramites"}


async def resolve_coords(loc: LocationItem | None) -> tuple[float, float] | None:
    if loc is None:
        return None
    if loc.lat is not None and loc.lng is not None:
        return (loc.lat, loc.lng)
    if loc.address and loc.address.strip() and loc.address != "Cualquier lugar":
        try:
            return await geocode_address(loc.address.strip())
        except Exception:
            return None
    return None


@router.post("/calculate-price")
async def calculate_price(body: PriceRequest, db: Session = Depends(get_session)):
    addresses = [s.destination.address for s in body.segments]
    is_raining = await check_rain()
    config_rows = db.query(FareConfig).all()
    tool_rows = db.query(Tool).filter(Tool.active == True).all()

    keyword_match = find_keyword_match(addresses, db)
    if keyword_match:
        breakdown = await calculate_full_price(
            segments=[],
            total_km=0.0,
            tools=body.tools,
            payment_method=body.payment_method,
            acompanante=body.acompanante,
            is_raining=is_raining,
            config_rows=config_rows,
            tool_rows=tool_rows,
            base_price=int(keyword_match.price),
        )
        return {
            "segments": [s.model_dump() for s in body.segments],
            "route": {
                "total_km": None,
                "route_type": "fixed_destination",
                "is_fixed_route": True,
                "fixed_reason": keyword_match.description or f"Tarifa fija: {keyword_match.destination_keyword}",
            },
            "breakdown": breakdown,
            "weather": {"is_raining": is_raining, "rain_surcharge": breakdown.get("rain_surcharge", 0)},
            "warnings": [],
        }

    # Proximity match: try to geocode each destination and check against
    # FixedPrice rows that have lat/lng + radius configured.
    # Rows with both keyword AND coords require BOTH to match.
    for seg in body.segments:
        dest_coords = await resolve_coords(seg.destination)
        if dest_coords:
            proximity_match = find_proximity_match(dest_coords[0], dest_coords[1], addresses, db)
            if proximity_match:
                breakdown = await calculate_full_price(
                    segments=[],
                    total_km=0.0,
                    tools=body.tools,
                    payment_method=body.payment_method,
                    acompanante=body.acompanante,
                    is_raining=is_raining,
                    config_rows=config_rows,
                    tool_rows=tool_rows,
                    base_price=int(proximity_match.price),
                )
                return {
                    "segments": [s.model_dump() for s in body.segments],
                    "route": {
                        "total_km": None,
                        "route_type": "fixed_destination",
                        "is_fixed_route": True,
                        "fixed_reason": proximity_match.description or f"Proximidad: destino cercano a punto de tarifa fija",
                    },
                    "breakdown": breakdown,
                    "weather": {"is_raining": is_raining, "rain_surcharge": breakdown.get("rain_surcharge", 0)},
                    "warnings": [],
                }

    # Build coordinate list for OSRM
    route_coords: list[tuple[float, float]] = []
    prev_coords = TULUA_CENTRO

    for idx, seg in enumerate(body.segments):
        # Use explicit origin or previous destination as origin
        if idx == 0 and seg.origin is not None:
            origin_coords = await resolve_coords(seg.origin)
            if origin_coords:
                route_coords.append(origin_coords)

        dest_coords = await resolve_coords(seg.destination)
        if dest_coords is None:
            continue

        if idx > 0 and not route_coords:
            route_coords.append(prev_coords)

        if route_coords and route_coords[-1] != dest_coords:
            route_coords.append(dest_coords)
        elif not route_coords:
            route_coords.append(dest_coords)

        prev_coords = dest_coords

    # If only one coord pair, add Tuluá centro as origin
    if len(route_coords) == 1:
        route_coords.insert(0, TULUA_CENTRO)

    # Deduplicate consecutive identical coords
    unique: list[tuple[float, float]] = []
    for c in route_coords:
        if not unique or c != unique[-1]:
            unique.append(c)

    total_km = await get_total_distance(unique) if len(unique) >= 2 else 0.0

    def is_any_destination(loc: LocationItem) -> bool:
        return (
            loc.address == "Cualquier lugar"
            or (not loc.address or not loc.address.strip())
        ) and not (loc.lat is not None and loc.lng is not None)

    # Determine segment prices
    seg_dicts = []
    for seg in body.segments:
        svc_config = SERVICE_TYPES.get(seg.service_type, {})
        service_has_coords = svc_config.get("has_coords", True)

        dest_is_any = is_any_destination(seg.destination)

        segment_has_coords = service_has_coords and not dest_is_any

        fp = None
        if not service_has_coords:
            fp = get_service_price(seg.service_type, db) or svc_config.get("default_price", 0)
        elif dest_is_any:
            fp = get_service_price(seg.service_type, db)

        seg_dicts.append({
            "service_type": seg.service_type,
            "label": svc_config.get("label", seg.service_type),
            "has_coords": segment_has_coords,
            "fixed_price": int(fp) if fp else 0,
        })

    breakdown = await calculate_full_price(
        segments=seg_dicts,
        total_km=total_km,
        tools=body.tools,
        payment_method=body.payment_method,
        acompanante=body.acompanante,
        is_raining=is_raining,
        config_rows=config_rows,
        tool_rows=tool_rows,
    )

    return {
        "segments": [s.model_dump() for s in body.segments],
        "route": {
            "total_km": total_km,
            "route_type": "calculated",
            "is_fixed_route": False,
        },
        "breakdown": breakdown,
        "weather": {"is_raining": is_raining, "rain_surcharge": breakdown.get("rain_surcharge", 0)},
        "warnings": [],
    }
