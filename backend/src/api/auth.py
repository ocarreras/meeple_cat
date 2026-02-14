from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_token
from src.models.database import get_db
from src.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    display_name: str


class TokenResponse(BaseModel):
    token: str
    user_id: str
    display_name: str


@router.post("/token", response_model=TokenResponse)
async def get_token(
    request: TokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Get or create user and return JWT token."""
    # Find or create user by display_name
    result = await db.execute(select(User).where(User.display_name == request.display_name))
    user = result.scalar_one_or_none()

    if not user:
        user = User(display_name=request.display_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_token(str(user.id), user.display_name)

    return TokenResponse(
        token=token,
        user_id=str(user.id),
        display_name=user.display_name,
    )
