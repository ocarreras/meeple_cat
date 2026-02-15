from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.cookies import clear_auth_cookies, set_auth_cookies
from src.auth.dependencies import get_current_user, get_current_user_optional
from src.auth.jwt import create_access_token, create_refresh_token, decode_jwt
from src.auth.models import UserAuth
from src.auth.providers import get_providers
from src.auth.schemas import TokenData
from src.auth.ws_auth import create_ws_ticket
from src.config import settings
from src.models.database import get_db
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProviderInfo(BaseModel):
    provider_id: str
    display_name: str


class UserInfoResponse(BaseModel):
    user_id: str
    display_name: str
    email: str | None
    avatar_url: str | None
    is_guest: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=list[ProviderInfo])
async def list_providers() -> list[ProviderInfo]:
    """List available OIDC login providers."""
    return [
        ProviderInfo(provider_id=p.provider_id, display_name=p.display_name)
        for p in get_providers().values()
    ]


@router.get("/{provider}/login")
async def oidc_login(provider: str, request: Request) -> RedirectResponse:
    """Redirect user to OIDC provider for login."""
    providers = get_providers()
    if provider not in providers:
        raise HTTPException(404, f"Unknown provider: {provider}")

    config = providers[provider]
    redis = request.app.state.redis

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", 300, provider.encode())

    params: dict[str, str] = {
        "client_id": config.client_id,
        "redirect_uri": f"{settings.frontend_url}/api/v1/auth/{provider}/callback",
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
    }

    if provider == "google":
        params["access_type"] = "offline"

    url = f"{config.authorize_url}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/{provider}/callback")
async def oidc_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle OIDC provider callback: exchange code, find/create user, set cookies."""
    providers = get_providers()
    if provider not in providers:
        raise HTTPException(404, f"Unknown provider: {provider}")

    config = providers[provider]
    redis = request.app.state.redis

    # Validate CSRF state
    stored = await redis.getdel(f"oauth_state:{state}")
    if not stored or stored.decode() != provider:
        raise HTTPException(400, "Invalid state parameter")

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{settings.frontend_url}/api/v1/auth/{provider}/callback",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_response.json()

        if "error" in token_data:
            logger.error(f"Token exchange failed for {provider}: {token_data}")
            raise HTTPException(400, f"Token exchange failed: {token_data.get('error_description', token_data['error'])}")

        provider_access_token = token_data["access_token"]

        # Fetch user info from provider
        userinfo_response = await client.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {provider_access_token}"},
        )
        userinfo = userinfo_response.json()

    # Extract user data
    provider_user_id = str(userinfo[config.id_field])
    email = userinfo.get(config.email_field)
    display_name = userinfo.get(config.name_field, f"Player-{provider_user_id[:8]}")
    avatar_url = userinfo.get(config.avatar_field)

    # Find or create user
    user = await _find_or_create_user(db, provider, provider_user_id, email, display_name, avatar_url)

    # Issue JWT pair
    access_jwt = create_access_token(str(user.id), user.display_name)
    refresh_jwt = create_refresh_token(str(user.id))

    # Store refresh token in Redis
    await redis.setex(
        f"refresh:{refresh_jwt}",
        settings.refresh_token_expire_days * 86400,
        str(user.id).encode(),
    )

    # Redirect to frontend with cookies set
    response = RedirectResponse(f"{settings.frontend_url}/auth/callback")
    set_auth_cookies(response, access_jwt, refresh_jwt)
    return response


@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Exchange a refresh token for new access + refresh tokens."""
    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        raise HTTPException(401, "No refresh token")

    payload = decode_jwt(refresh_tok)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid token type")

    redis = request.app.state.redis

    # Check token not revoked
    stored = await redis.get(f"refresh:{refresh_tok}")
    if not stored:
        raise HTTPException(401, "Token revoked or expired")

    user_id = payload["sub"]
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")

    # Issue new token pair
    new_access = create_access_token(str(user.id), user.display_name)
    new_refresh = create_refresh_token(str(user.id))

    # Rotate: revoke old, store new
    await redis.delete(f"refresh:{refresh_tok}")
    await redis.setex(
        f"refresh:{new_refresh}",
        settings.refresh_token_expire_days * 86400,
        str(user.id).encode(),
    )

    response = JSONResponse({"status": "ok"})
    set_auth_cookies(response, new_access, new_refresh)
    return response


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Clear auth cookies and revoke refresh token."""
    refresh_tok = request.cookies.get("refresh_token")
    if refresh_tok:
        redis = request.app.state.redis
        await redis.delete(f"refresh:{refresh_tok}")

    response = JSONResponse({"status": "ok"})
    clear_auth_cookies(response)
    return response


@router.get("/me", response_model=UserInfoResponse)
async def get_me(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserInfoResponse:
    """Return current authenticated user's info."""
    user = await db.get(User, current_user.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    return UserInfoResponse(
        user_id=str(user.id),
        display_name=user.display_name,
        email=user.email,
        avatar_url=user.avatar_url,
        is_guest=user.is_guest,
    )


@router.post("/ws-ticket")
async def get_ws_ticket(
    request: Request,
    current_user: TokenData = Depends(get_current_user),
) -> dict[str, str]:
    """Issue a single-use, short-lived WebSocket connection ticket."""
    redis = request.app.state.redis
    ticket = await create_ws_ticket(redis, current_user.user_id, current_user.display_name)
    return {"ticket": ticket}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _find_or_create_user(
    db: AsyncSession,
    provider: str,
    provider_id: str,
    email: str | None,
    display_name: str,
    avatar_url: str | None,
) -> User:
    """Find existing user by provider link or email, or create a new one."""
    # 1. Look for existing auth with this provider + provider_id
    result = await db.execute(
        select(UserAuth).where(
            UserAuth.provider == provider,
            UserAuth.provider_id == provider_id,
        )
    )
    existing_auth = result.scalar_one_or_none()

    if existing_auth:
        user = await db.get(User, existing_auth.user_id)
        if user:
            # Update avatar on each login
            user.avatar_url = avatar_url or user.avatar_url
            await db.flush()
            return user

    # 2. Check if email matches an existing user (account linking)
    if email:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        if user:
            # Link this provider to existing account
            new_auth = UserAuth(
                user_id=user.id,
                provider=provider,
                provider_id=provider_id,
            )
            db.add(new_auth)
            user.avatar_url = avatar_url or user.avatar_url
            user.is_guest = False
            await db.flush()
            return user

    # 3. Create new user — handle display_name collisions
    final_name = await _unique_display_name(db, display_name)

    user = User(
        display_name=final_name,
        email=email,
        avatar_url=avatar_url,
        is_guest=False,
    )
    db.add(user)
    await db.flush()

    auth_entry = UserAuth(
        user_id=user.id,
        provider=provider,
        provider_id=provider_id,
    )
    db.add(auth_entry)
    await db.flush()

    return user


async def _unique_display_name(db: AsyncSession, name: str) -> str:
    """Ensure display_name is unique by appending a numeric suffix if needed."""
    result = await db.execute(select(User).where(User.display_name == name))
    if result.scalar_one_or_none() is None:
        return name

    for i in range(2, 100):
        candidate = f"{name}_{i}"
        result = await db.execute(select(User).where(User.display_name == candidate))
        if result.scalar_one_or_none() is None:
            return candidate

    # Extremely unlikely fallback
    return f"{name}_{secrets.token_hex(4)}"
