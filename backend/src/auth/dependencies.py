from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import decode_token
from src.auth.schemas import TokenData
from src.config import settings
from src.models.database import get_db
from src.models.user import User

# auto_error=False so missing Bearer header doesn't reject cookie-authenticated users
optional_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> TokenData:
    """Authenticate via cookie first, then Bearer header. Raises 401 if neither works."""
    # 1. Try access_token cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        try:
            return decode_token(cookie_token)
        except HTTPException:
            pass  # Fall through to Bearer (cookie may be expired/stale)

    # 2. Fall back to Bearer header
    if credentials:
        return decode_token(credentials.credentials)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


async def get_admin_user(
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenData:
    """Require the authenticated user to be the admin. Raises 403 otherwise."""
    user = await db.get(User, current_user.user_id)
    if not user or user.email != settings.admin_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> TokenData | None:
    """Same as get_current_user but returns None instead of raising."""
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        try:
            return decode_token(cookie_token)
        except HTTPException:
            pass

    if credentials:
        try:
            return decode_token(credentials.credentials)
        except HTTPException:
            pass

    return None
