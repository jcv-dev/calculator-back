import os
from fastapi import Request, HTTPException, status
from dotenv import load_dotenv

load_dotenv()


def get_admin_password():
    pw = os.getenv("ADMIN_PASSWORD")
    if not pw:
        raise RuntimeError("ADMIN_PASSWORD environment variable is not set")
    return pw


def get_session_secret():
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        raise RuntimeError("SESSION_SECRET environment variable is not set")
    return secret


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
