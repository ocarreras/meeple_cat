# 05 — Auth System Design

Authentication via OpenID Connect with Google, GitHub, and Discord. JWT-based
session management. Minimal friction — users can play immediately after first
login.

---

## 1. OIDC Provider Configuration

### 1.1 Provider Registry

```python
from pydantic import BaseModel

class OIDCProviderConfig(BaseModel):
    provider_id: str             # "google", "github", "discord"
    display_name: str
    client_id: str               # From env vars
    client_secret: str           # From env vars
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]
    # Mapping from provider's user info to our user model
    id_field: str                # Field name for unique user ID
    email_field: str
    name_field: str
    avatar_field: str

PROVIDERS = {
    "google": OIDCProviderConfig(
        provider_id="google",
        display_name="Google",
        client_id=env("GOOGLE_CLIENT_ID"),
        client_secret=env("GOOGLE_CLIENT_SECRET"),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        scopes=["openid", "email", "profile"],
        id_field="sub",
        email_field="email",
        name_field="name",
        avatar_field="picture",
    ),
    "github": OIDCProviderConfig(
        provider_id="github",
        display_name="GitHub",
        client_id=env("GITHUB_CLIENT_ID"),
        client_secret=env("GITHUB_CLIENT_SECRET"),
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        scopes=["read:user", "user:email"],
        id_field="id",
        email_field="email",
        name_field="login",           # GitHub uses "login" for username
        avatar_field="avatar_url",
    ),
    "discord": OIDCProviderConfig(
        provider_id="discord",
        display_name="Discord",
        client_id=env("DISCORD_CLIENT_ID"),
        client_secret=env("DISCORD_CLIENT_SECRET"),
        authorize_url="https://discord.com/api/oauth2/authorize",
        token_url="https://discord.com/api/oauth2/token",
        userinfo_url="https://discord.com/api/users/@me",
        scopes=["identify", "email"],
        id_field="id",
        email_field="email",
        name_field="username",
        avatar_field="avatar",        # Needs URL construction
    ),
}
```

### 1.2 Provider-Specific Quirks

- **GitHub**: Not strictly OIDC. Uses OAuth2 with a custom userinfo endpoint.
  Token endpoint returns `application/x-www-form-urlencoded` by default —
  must send `Accept: application/json`. Email may require a separate call to
  `/user/emails` if the user has a private email.

- **Discord**: Avatar field is just a hash. Full URL:
  `https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png`

- **Google**: Standard OIDC, no quirks.

---

## 2. Auth Flow

### 2.1 Login Initiation

```python
@auth_router.get("/auth/{provider}/login")
async def login(provider: str, request: Request):
    if provider not in PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    config = PROVIDERS[provider]

    # Generate state parameter (CSRF protection)
    state = secrets.token_urlsafe(32)
    await redis.setex(f"oauth_state:{state}", 300, provider)  # 5 min TTL

    # Build authorization URL
    params = {
        "client_id": config.client_id,
        "redirect_uri": f"{settings.BASE_URL}/auth/{provider}/callback",
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
    }

    # Provider-specific params
    if provider == "google":
        params["access_type"] = "offline"  # Get refresh token
    if provider == "discord":
        params["prompt"] = "consent"

    url = f"{config.authorize_url}?{urlencode(params)}"
    return RedirectResponse(url)
```

### 2.2 Callback Handling

```python
@auth_router.get("/auth/{provider}/callback")
async def callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # Validate state (CSRF)
    stored_provider = await redis.getdel(f"oauth_state:{state}")
    if not stored_provider or stored_provider.decode() != provider:
        raise HTTPException(400, "Invalid state parameter")

    config = PROVIDERS[provider]

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{settings.BASE_URL}/auth/{provider}/callback",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_response.json()

        if "error" in token_data:
            raise HTTPException(400, f"Token exchange failed: {token_data['error']}")

        access_token = token_data["access_token"]

        # Fetch user info
        userinfo_response = await client.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo = userinfo_response.json()

    # Extract user data using provider field mappings
    provider_id = str(userinfo[config.id_field])
    email = userinfo.get(config.email_field)
    display_name = userinfo.get(config.name_field, f"Player-{provider_id[:8]}")
    avatar_url = _resolve_avatar(provider, userinfo, config)

    # GitHub: fetch email separately if private
    if provider == "github" and not email:
        email = await _fetch_github_email(access_token)

    # Find or create user
    user = await _find_or_create_user(
        db, provider, provider_id, email, display_name, avatar_url
    )

    # Issue JWT pair
    access_jwt = create_access_token(user)
    refresh_jwt = create_refresh_token(user)

    # Store refresh token in Redis
    await redis.setex(
        f"refresh:{refresh_jwt}",
        settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        user.id,
    )

    # Redirect to frontend with tokens
    # (Frontend reads tokens from URL fragment or cookie)
    redirect_url = f"{settings.FRONTEND_URL}/auth/callback"
    response = RedirectResponse(redirect_url)
    response.set_cookie(
        "access_token", access_jwt,
        httponly=True, secure=True, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
    )
    response.set_cookie(
        "refresh_token", refresh_jwt,
        httponly=True, secure=True, samesite="lax",
        path="/auth/refresh",  # Only sent to refresh endpoint
        max_age=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
    )
    return response
```

### 2.3 Account Linking

Users may log in with different providers that share the same email.
Strategy: **link by email if verified**.

```python
async def _find_or_create_user(
    db: AsyncSession,
    provider: str,
    provider_id: str,
    email: str | None,
    display_name: str,
    avatar_url: str | None,
) -> User:
    # First: look for existing auth with this provider + provider_id
    auth = await db.execute(
        select(UserAuth).where(
            UserAuth.provider == provider,
            UserAuth.provider_id == provider_id,
        )
    )
    existing_auth = auth.scalar_one_or_none()

    if existing_auth:
        # Returning user — update profile
        user = await db.get(User, existing_auth.user_id)
        user.last_seen_at = datetime.utcnow()
        user.avatar_url = avatar_url or user.avatar_url
        await db.commit()
        return user

    # Check if email matches an existing user (account linking)
    if email:
        existing_user = await db.execute(
            select(User).where(User.email == email)
        )
        user = existing_user.scalar_one_or_none()
        if user:
            # Link this provider to the existing account
            new_auth = UserAuth(
                user_id=user.id,
                provider=provider,
                provider_id=provider_id,
            )
            db.add(new_auth)
            await db.commit()
            return user

    # New user
    user = User(
        id=str(uuid4()),
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(user)

    auth_entry = UserAuth(
        user_id=user.id,
        provider=provider,
        provider_id=provider_id,
    )
    db.add(auth_entry)
    await db.commit()
    return user
```

Updated DB model to support multiple auth providers per user:

```sql
users (id PK, email, display_name, avatar_url, bio, country, created_at, last_seen_at)
user_auths (id PK, user_id FK, provider, provider_id, created_at)
  -- UNIQUE (provider, provider_id)
  -- INDEX (user_id)
```

---

## 3. JWT Implementation

### 3.1 Token Creation

```python
from jose import jwt
from datetime import datetime, timedelta

SECRET_KEY = env("JWT_SECRET_KEY")   # 256-bit random key
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)

def create_access_token(user: User) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": user.id,
        "name": user.display_name,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user: User) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": user.id,
        "type": "refresh",
        "jti": str(uuid4()),         # Unique token ID for revocation
        "iat": now,
        "exp": now + REFRESH_TOKEN_EXPIRE,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.JWTError:
        raise HTTPException(401, "Invalid token")
```

### 3.2 Token Refresh

```python
@auth_router.post("/auth/refresh")
async def refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "No refresh token")

    payload = decode_jwt(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid token type")

    # Check token not revoked
    stored = await redis.get(f"refresh:{refresh_token}")
    if not stored:
        raise HTTPException(401, "Token revoked or expired")

    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")

    # Issue new tokens
    new_access = create_access_token(user)
    new_refresh = create_refresh_token(user)

    # Rotate: revoke old refresh, store new
    await redis.delete(f"refresh:{refresh_token}")
    await redis.setex(
        f"refresh:{new_refresh}",
        int(REFRESH_TOKEN_EXPIRE.total_seconds()),
        user.id,
    )

    response = JSONResponse({"status": "ok"})
    response.set_cookie("access_token", new_access, httponly=True, secure=True, samesite="lax",
                         max_age=int(ACCESS_TOKEN_EXPIRE.total_seconds()))
    response.set_cookie("refresh_token", new_refresh, httponly=True, secure=True, samesite="lax",
                         path="/auth/refresh", max_age=int(REFRESH_TOKEN_EXPIRE.total_seconds()))
    return response
```

### 3.3 Logout

```python
@auth_router.post("/auth/logout")
async def logout(request: Request):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        await redis.delete(f"refresh:{refresh_token}")

    response = JSONResponse({"status": "ok"})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return response
```

---

## 4. WebSocket Authentication

WebSockets can't use HTTP-only cookies in a standard way. Strategy:

```
1. Client makes REST call to /api/v1/auth/ws-ticket
   (authenticated via cookie)
2. Server returns a short-lived ticket (30s, single-use, stored in Redis)
3. Client connects to /ws/game/{match_id}?ticket={ticket}
4. Server validates ticket, extracts user_id, deletes ticket from Redis
```

```python
@v1_router.post("/auth/ws-ticket")
async def get_ws_ticket(user: User = Depends(get_current_user)):
    ticket = secrets.token_urlsafe(32)
    await redis.setex(f"ws_ticket:{ticket}", 30, user.id)  # 30s TTL
    return {"ticket": ticket}

async def authenticate_ws(ticket: str) -> User:
    user_id = await redis.getdel(f"ws_ticket:{ticket}")  # Single-use
    if not user_id:
        raise AuthError("Invalid or expired ticket")
    user = await db.get(User, user_id.decode())
    if not user:
        raise AuthError("User not found")
    return user
```

---

## 5. Authorization

### 5.1 Resource-Level Access

Simple ownership-based authorization:

| Resource | Rule |
|---|---|
| Edit profile | Only own profile |
| Manage bots | Only own bots |
| Start game | Only room creator |
| Submit action | Only players in the match, only during their turn |
| View replay | Anyone (public) |
| Admin actions | Role == "admin" |

```python
async def require_owner(resource_owner_id: str, user: User = Depends(get_current_user)):
    if user.id != resource_owner_id and user.role != "admin":
        raise HTTPException(403, "Not authorized")

# Game-level auth is handled by GameSession._validate_envelope()
```

### 5.2 Role Model

Two roles: `user` (default) and `admin`. Stored in the users table.
Admin is for platform management (ban users, delete games, etc.).
No need for anything more complex.

---

## 6. Library Choice

**authlib** for OIDC:
- Mature, well-maintained
- Handles OAuth2/OIDC flows cleanly
- Good FastAPI integration via Starlette

**python-jose** for JWT:
- Lightweight, focused on JWT
- HS256 is sufficient for single-server (no need for RS256 key distribution)

---

## 7. Module Structure

```
backend/src/auth/
├── __init__.py
├── config.py          # Provider configurations, JWT settings
├── routes.py          # Auth endpoints (login, callback, refresh, logout)
├── jwt.py             # Token creation, validation, decoding
├── providers.py       # Provider-specific logic (GitHub email, Discord avatar)
├── dependencies.py    # FastAPI dependencies (get_current_user, etc.)
├── models.py          # UserAuth SQLAlchemy model
└── ws_auth.py         # WebSocket ticket auth
```
