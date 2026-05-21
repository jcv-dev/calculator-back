import re
import math
from sqlalchemy.orm import Session
from models import FixedPrice


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_keyword_match(addresses: list[str], db: Session) -> FixedPrice | None:
    rows = db.query(FixedPrice).filter(
        FixedPrice.destination_keyword.isnot(None),
        FixedPrice.lat.is_(None),
    ).all()

    for addr in addresses:
        addr_lower = addr.lower()
        for row in rows:
            pattern = re.compile(
                r'\b' + re.escape(row.destination_keyword.lower()) + r'\b', re.IGNORECASE
            )
            if pattern.search(addr_lower):
                return row

    return None


def find_proximity_match(
    dest_lat: float, dest_lng: float, addresses: list[str], db: Session
) -> FixedPrice | None:
    rows = db.query(FixedPrice).filter(
        FixedPrice.lat.isnot(None),
        FixedPrice.lng.isnot(None),
        FixedPrice.radius_km.isnot(None),
    ).all()

    best = None
    best_dist = float('inf')

    for row in rows:
        if row.destination_keyword:
            keyword_matches = any(
                re.search(
                    r'\b' + re.escape(row.destination_keyword.lower()) + r'\b',
                    addr.lower()
                )
                for addr in addresses
            )
            if not keyword_matches:
                continue

        dist = _haversine_km(dest_lat, dest_lng, row.lat, row.lng)
        if dist <= row.radius_km and dist < best_dist:
            best = row
            best_dist = dist

    return best


def get_service_price(service_type: str, db: Session) -> float | None:
    row = db.query(FixedPrice).filter(
        FixedPrice.service_type == service_type,
        FixedPrice.destination_keyword.is_(None),
        FixedPrice.lat.is_(None),
    ).first()

    if row:
        return row.price
    return None
