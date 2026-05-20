import os
from fastapi import APIRouter

router = APIRouter(prefix="/api/config")


@router.get("/whatsapp")
async def get_whatsapp_number():
    number = os.getenv("WHATSAPP_NUMBER", "")
    return {"number": number}
