from sqlalchemy.orm import Session
from models import FareConfig, FixedPrice, Tool

DEFAULT_CONFIG = {
    "BASE_FARE": (4000, "Minimum fare up to 1.0 km"),
    "EXTRA_STOP_FEE": (0, "Applied to every stop beyond the first delivery destination"),
    "METODO_NEQUI_SURCHARGE": (500, "Handling fee for Nequi logistics"),
    "RAIN_SURCHARGE": (500, "Dynamic fee auto-applied if OpenWeather API detects rain"),
    "WAIT_FEE": (2000, "Surcharge for wait times over 15 min (applied per each 15 min)"),
    "TIER_1_LIMIT": (1.0, "Upper bound of tier 1 (km); distances ≤ this get flat BASE_FARE"),
    "TIER_1_RATE": (0, "Per-km COP rate within tier 1 (0 = flat-fee zone)"),
    "TIER_2_LIMIT": (1.5, "Upper bound of tier 2 (km)"),
    "TIER_2_RATE": (150, "Per-km COP rate within tier 2"),
    "TIER_3_LIMIT": (3.0, "Upper bound of tier 3 (km)"),
    "TIER_3_RATE": (350, "Per-km COP rate within tier 3"),
    "TIER_4_LIMIT": (3.5, "Upper bound of tier 4 (km)"),
    "TIER_4_RATE": (500, "Per-km COP rate within tier 4"),
    "TIER_5_LIMIT": (4.0, "Upper bound of tier 5 (km)"),
    "TIER_5_RATE": (550, "Per-km COP rate within tier 5"),
    "TIER_6_LIMIT": (4.5, "Upper bound of tier 6 (km)"),
    "TIER_6_RATE": (700, "Per-km COP rate within tier 6"),
    "TIER_7_LIMIT": (5.0, "Upper bound of tier 7 (km)"),
    "TIER_7_RATE": (750, "Per-km COP rate within tier 7"),
    "FINAL_RATE": (950, "Per-km COP rate for distance beyond the last tier limit"),
    "ACOMPANANTE_MULTIPLIER": (1.0, "Multiplier applied when acompañante is enabled (1.0 = no extra cost)"),
}

DEFAULT_FIXED_PRICES = [
    {
        "service_type": None,
        "destination_keyword": "cali",
        "price": 120000,
        "description": "Tarifa fija Tuluá → Cali (cualquier servicio)",
        "lat": 3.4516,
        "lng": -76.5320,
        "radius_km": 20,
    },
    {
        "service_type": None,
        "destination_keyword": "buga",
        "price": 35000,
        "description": "Tarifa fija Tuluá → Buga (cualquier servicio)",
        "lat": 3.9000,
        "lng": -76.3021,
        "radius_km": 15,
    },
    {
        "service_type": None,
        "destination_keyword": "aeropuerto",
        "price": 150000,
        "description": "Tarifa fija Tuluá → Aeropuerto Alfonso Bonilla Aragón",
        "lat": 3.5432,
        "lng": -76.3816,
        "radius_km": 15,
    },
    {
        "service_type": "purchases",
        "destination_keyword": None,
        "price": 7000,
        "description": "Tarifa base para servicio de compras",
    },
    {
        "service_type": "bancarios",
        "destination_keyword": None,
        "price": 5000,
        "description": "Tarifa base para trámites bancarios",
    },
]

DEFAULT_TOOLS = [
    {
        "key": "canasta",
        "label": "Canasta",
        "description": "Pedidos pesados o voluminosos",
        "surcharge": 0,
        "material_symbol": "shopping_basket",
        "color": "#d97706",
        "active": True,
    },
    {
        "key": "maletin",
        "label": "Maletín",
        "description": "Bolso térmico para entregas",
        "surcharge": 0,
        "material_symbol": "work",
        "color": "#3b82f6",
        "active": True,
    },
]


def seed_config(db: Session):
    for key, (value, description) in DEFAULT_CONFIG.items():
        existing = db.query(FareConfig).filter(FareConfig.key == key).first()
        if not existing:
            db.add(FareConfig(key=key, value=float(value), description=description))

    for fp in DEFAULT_FIXED_PRICES:
        existing = None
        if fp["destination_keyword"]:
            existing = db.query(FixedPrice).filter(
                FixedPrice.destination_keyword == fp["destination_keyword"]
            ).first()
        elif fp["service_type"]:
            existing = db.query(FixedPrice).filter(
                FixedPrice.service_type == fp["service_type"],
                FixedPrice.destination_keyword.is_(None),
            ).first()

        if not existing:
            db.add(FixedPrice(
                service_type=fp["service_type"],
                destination_keyword=fp["destination_keyword"],
                price=float(fp["price"]),
                description=fp["description"],
                lat=fp.get("lat"),
                lng=fp.get("lng"),
                radius_km=fp.get("radius_km"),
            ))

    for tool in DEFAULT_TOOLS:
        existing = db.query(Tool).filter(Tool.key == tool["key"]).first()
        if not existing:
            db.add(Tool(
                key=tool["key"],
                label=tool["label"],
                description=tool["description"],
                surcharge=float(tool["surcharge"]),
                material_symbol=tool["material_symbol"],
                color=tool.get("color", ""),
                active=tool["active"],
            ))

    db.commit()
