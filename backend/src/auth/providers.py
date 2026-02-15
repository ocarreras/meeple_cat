from __future__ import annotations

from pydantic import BaseModel

from src.config import settings


class OIDCProviderConfig(BaseModel):
    provider_id: str
    display_name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: list[str]
    id_field: str
    email_field: str
    name_field: str
    avatar_field: str


def get_providers() -> dict[str, OIDCProviderConfig]:
    """Build provider registry from settings. Only includes providers with configured credentials."""
    providers: dict[str, OIDCProviderConfig] = {}

    if settings.google_client_id and settings.google_client_secret:
        providers["google"] = OIDCProviderConfig(
            provider_id="google",
            display_name="Google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
            scopes=["openid", "email", "profile"],
            id_field="sub",
            email_field="email",
            name_field="name",
            avatar_field="picture",
        )

    return providers
