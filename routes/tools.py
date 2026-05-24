from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_session
from models import Tool

router = APIRouter(prefix="/api")


@router.get("/tools")
async def list_active_tools(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Tool).where(Tool.active == True).order_by(Tool.key))
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
