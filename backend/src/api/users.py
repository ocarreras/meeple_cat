from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import TokenData, get_current_user
from src.models.database import get_db
from src.models.match import Match, MatchPlayer
from src.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UserProfileResponse(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None
    is_guest: bool
    games_played: int
    games_won: int


class MatchHistoryEntry(BaseModel):
    match_id: str
    game_id: str
    status: str
    started_at: str | None
    ended_at: str | None
    seat_index: int
    result: str | None
    score: float | None
    players: list[MatchPlayerInfo]


class MatchPlayerInfo(BaseModel):
    display_name: str
    seat_index: int
    score: float | None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Get a user's public profile."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Count games played and won
    games_played = await db.scalar(
        select(func.count()).select_from(MatchPlayer).where(
            MatchPlayer.user_id == user.id,
            MatchPlayer.is_bot == False,  # noqa: E712
        )
    )

    games_won = await db.scalar(
        select(func.count()).select_from(MatchPlayer).where(
            MatchPlayer.user_id == user.id,
            MatchPlayer.result == "win",
        )
    )

    return UserProfileResponse(
        user_id=str(user.id),
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_guest=user.is_guest,
        games_played=games_played or 0,
        games_won=games_won or 0,
    )


@router.get("/{user_id}/matches", response_model=list[MatchHistoryEntry])
async def get_user_matches(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[MatchHistoryEntry]:
    """Get a user's match history."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Get user's match player entries, ordered by most recent
    result = await db.execute(
        select(MatchPlayer)
        .where(
            MatchPlayer.user_id == user.id,
            MatchPlayer.is_bot == False,  # noqa: E712
        )
        .join(Match)
        .order_by(Match.created_at.desc())
        .offset(offset)
        .limit(limit)
        .options(selectinload(MatchPlayer.match).selectinload(Match.players).selectinload(MatchPlayer.user))
    )
    match_players = result.scalars().all()

    entries = []
    for mp in match_players:
        match = mp.match
        players_info = [
            MatchPlayerInfo(
                display_name=p.user.display_name if p.user else f"Bot ({p.bot_id})",
                seat_index=p.seat_index,
                score=p.score,
            )
            for p in sorted(match.players, key=lambda p: p.seat_index)
        ]

        entries.append(MatchHistoryEntry(
            match_id=str(match.id),
            game_id=match.game_id,
            status=match.status,
            started_at=match.started_at.isoformat() if match.started_at else None,
            ended_at=match.ended_at.isoformat() if match.ended_at else None,
            seat_index=mp.seat_index,
            result=mp.result,
            score=mp.score,
            players=players_info,
        ))

    return entries


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    body: UpdateProfileRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Update the current user's profile."""
    user = await db.get(User, current_user.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    if body.display_name is not None:
        # Check uniqueness
        existing = await db.execute(
            select(User).where(User.display_name == body.display_name, User.id != user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Display name already taken")
        user.display_name = body.display_name

    await db.flush()

    games_played = await db.scalar(
        select(func.count()).select_from(MatchPlayer).where(
            MatchPlayer.user_id == user.id,
            MatchPlayer.is_bot == False,  # noqa: E712
        )
    )
    games_won = await db.scalar(
        select(func.count()).select_from(MatchPlayer).where(
            MatchPlayer.user_id == user.id,
            MatchPlayer.result == "win",
        )
    )

    return UserProfileResponse(
        user_id=str(user.id),
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_guest=user.is_guest,
        games_played=games_played or 0,
        games_won=games_won or 0,
    )
