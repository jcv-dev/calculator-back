from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_session
from models import Tool

router = APIRouter(prefix="/api")


@router.get("/tools")
async def list_active_tools(db: Session = Depends(get_session)):
    rows = db.query(Tool).filter(Tool.active == True).order_by(Tool.key).all()
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
