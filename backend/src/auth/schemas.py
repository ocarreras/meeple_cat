from __future__ import annotations

from pydantic import BaseModel


class TokenData(BaseModel):
    user_id: str
    display_name: str
