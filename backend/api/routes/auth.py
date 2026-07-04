from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared.auth import get_user, verify_password, create_session

router = APIRouter()

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

@router.post("/api/auth/login")
async def login(request: LoginRequest):
    user = await get_user(request.username)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = await create_session(user["username"], user["role"])
    return {
        "token": token,
        "username": user["username"],
        "role": user["role"],
        "display_name": user.get("display_name", user["username"]),
    }
