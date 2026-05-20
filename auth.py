import os
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()


def get_admin_password():
    return os.getenv("ADMIN_PASSWORD", "admin")


def get_session_secret():
    return os.getenv("SESSION_SECRET", "default-secret-change-me")


async def login_user(request: Request, password: str) -> bool:
    if password == get_admin_password():
        request.session["admin"] = True
        return True
    return False


async def logout_user(request: Request):
    request.session.pop("admin", None)


async def require_admin(request: Request):
    if not request.session.get("admin"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
