from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import get_admin_user
from src.auth.schemas import TokenData
from src.engine.event_store import EventStore
from src.engine.models import GameResult
from src.models.database import get_db
from src.models.match import Match, MatchPlayer
from src.models.room import GameRoom, GameRoomSeat
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AdminPlayerInfo(BaseModel):
    display_name: str
    user_id: str
    is_bot: bool
    score: float | None


class AdminMatchInfo(BaseModel):
    match_id: str
    game_id: str
    status: str
    players: list[AdminPlayerInfo]
    started_at: str | None
    has_active_session: bool


class AdminRoomInfo(BaseModel):
    room_id: str
    game_id: str
    status: str
    creator_name: str
    created_at: str
    player_count: int
    max_players: int
    match_id: str | None


class AdminOverviewResponse(BaseModel):
    active_matches: list[AdminMatchInfo]
    active_rooms: list[AdminRoomInfo]


class AdminUserInfo(BaseModel):
    user_id: str
    display_name: str
    email: str | None
    is_guest: bool
    is_banned: bool
    created_at: str
    games_played: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=AdminOverviewResponse)
async def admin_overview(
    request: Request,
    current_user: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminOverviewResponse:
    """Get active matches and rooms for admin dashboard."""
    session_manager = request.app.state.session_manager

    # Active matches
    result = await db.execute(
        select(Match)
        .where(Match.status == "active")
        .options(selectinload(Match.players).selectinload(MatchPlayer.user))
        .order_by(Match.started_at.desc())
    )
    matches = result.scalars().all()

    active_matches = []
    for match in matches:
        match_id_str = str(match.id)
        session = session_manager.get_session(match_id_str)
        players = []
        for mp in match.players:
            players.append(AdminPlayerInfo(
                display_name=mp.user.display_name if mp.user else "Unknown",
                user_id=str(mp.user_id),
                is_bot=mp.is_bot,
                score=mp.score,
            ))
        active_matches.append(AdminMatchInfo(
            match_id=match_id_str,
            game_id=match.game_id,
            status=match.status,
            players=players,
            started_at=match.started_at.isoformat() if match.started_at else None,
            has_active_session=session is not None,
        ))

    # Active rooms
    result = await db.execute(
        select(GameRoom)
        .where(GameRoom.status.in_(["waiting", "in_game"]))
        .options(selectinload(GameRoom.seats), selectinload(GameRoom.creator))
        .order_by(GameRoom.created_at.desc())
    )
    rooms = result.scalars().all()

    active_rooms = []
    for room in rooms:
        player_count = sum(1 for s in room.seats if s.user_id is not None)
        active_rooms.append(AdminRoomInfo(
            room_id=str(room.id),
            game_id=room.game_id,
            status=room.status,
            creator_name=room.creator.display_name if room.creator else "Unknown",
            created_at=room.created_at.isoformat(),
            player_count=player_count,
            max_players=room.max_players,
            match_id=str(room.match_id) if room.match_id else None,
        ))

    return AdminOverviewResponse(
        active_matches=active_matches,
        active_rooms=active_rooms,
    )


@router.post("/force-finish/{match_id}")
async def admin_force_finish(
    match_id: str,
    request: Request,
    current_user: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Force-finish an active match."""
    try:
        match_uuid = UUID(match_id)
    except ValueError:
        raise HTTPException(400, "Invalid match ID")

    match = await db.get(Match, match_uuid)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != "active":
        raise HTTPException(400, f"Match is not active (status: {match.status})")

    session_manager = request.app.state.session_manager
    session = session_manager.get_session(match_id)

    if session:
        # Force-finish via session (broadcasts game_over to connected clients)
        async with session._lock:
            session._event_store = EventStore(db)
            final_scores = {k: float(v) for k, v in session.state.scores.items()}
            result = GameResult(
                winners=[],
                final_scores=final_scores,
                reason="admin_terminated",
            )
            await session._finish_game(result)

        session_manager.remove_session(match_id)

        # Clean up Redis state
        state_store = request.app.state.session_manager._state_store
        await state_store.delete_state(match_id)

        # Clean up WebSocket connections
        cm = request.app.state.connection_manager
        cm.cleanup_match(match_id)
    else:
        # No live session — update DB directly
        match.status = "abandoned"
        match.ended_at = datetime.now(timezone.utc)

        result = await db.execute(
            select(MatchPlayer).where(MatchPlayer.match_id == match_uuid)
        )
        for mp in result.scalars().all():
            mp.result = "abandoned"

    # Update associated room if any
    result = await db.execute(
        select(GameRoom).where(GameRoom.match_id == match_uuid)
    )
    room = result.scalar_one_or_none()
    if room:
        room.status = "waiting"
        room.match_id = None

    await db.commit()
    logger.info(f"Admin force-finished match {match_id}")
    return {"ok": True}


@router.post("/delete-room/{room_id}")
async def admin_delete_room(
    room_id: str,
    request: Request,
    current_user: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a room. If it has an active match, force-finish it too."""
    try:
        room_uuid = UUID(room_id)
    except ValueError:
        raise HTTPException(400, "Invalid room ID")

    room = await db.get(GameRoom, room_uuid)
    if not room:
        raise HTTPException(404, "Room not found")

    # If room has an active match, force-finish it
    if room.match_id:
        match = await db.get(Match, room.match_id)
        if match and match.status == "active":
            session_manager = request.app.state.session_manager
            match_id_str = str(room.match_id)
            session = session_manager.get_session(match_id_str)

            if session:
                async with session._lock:
                    session._event_store = EventStore(db)
                    final_scores = {k: float(v) for k, v in session.state.scores.items()}
                    game_result = GameResult(
                        winners=[],
                        final_scores=final_scores,
                        reason="admin_terminated",
                    )
                    await session._finish_game(game_result)

                session_manager.remove_session(match_id_str)
                state_store = session_manager._state_store
                await state_store.delete_state(match_id_str)
                cm = request.app.state.connection_manager
                cm.cleanup_match(match_id_str)
            else:
                match.status = "abandoned"
                match.ended_at = datetime.now(timezone.utc)
                result = await db.execute(
                    select(MatchPlayer).where(MatchPlayer.match_id == room.match_id)
                )
                for mp in result.scalars().all():
                    mp.result = "abandoned"

    # Delete seats then room
    await db.execute(
        select(GameRoomSeat).where(GameRoomSeat.room_id == room_uuid)
    )
    result = await db.execute(
        select(GameRoomSeat).where(GameRoomSeat.room_id == room_uuid)
    )
    for seat in result.scalars().all():
        await db.delete(seat)

    await db.delete(room)
    await db.commit()
    logger.info(f"Admin deleted room {room_id}")
    return {"ok": True}


@router.get("/users", response_model=list[AdminUserInfo])
async def admin_list_users(
    current_user: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[AdminUserInfo]:
    """List users with optional search filter."""
    # Subquery for games_played count
    games_played_subq = (
        select(
            MatchPlayer.user_id,
            func.count(MatchPlayer.id).label("games_played"),
        )
        .group_by(MatchPlayer.user_id)
        .subquery()
    )

    query = (
        select(User, games_played_subq.c.games_played)
        .outerjoin(games_played_subq, User.id == games_played_subq.c.user_id)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if search:
        pattern = f"%{search}%"
        query = query.where(
            User.display_name.ilike(pattern) | User.email.ilike(pattern)
        )

    result = await db.execute(query)
    rows = result.all()

    return [
        AdminUserInfo(
            user_id=str(user.id),
            display_name=user.display_name,
            email=user.email,
            is_guest=user.is_guest,
            is_banned=user.is_banned,
            created_at=user.created_at.isoformat(),
            games_played=games_played or 0,
        )
        for user, games_played in rows
    ]


@router.post("/ban/{user_id}")
async def admin_ban_user(
    user_id: str,
    request: Request,
    current_user: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ban a user. Force-finishes any of their active games."""
    if user_id == current_user.user_id:
        raise HTTPException(400, "Cannot ban yourself")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(404, "User not found")

    user.is_banned = True

    # Force-finish any active games this user is in
    session_manager = request.app.state.session_manager
    for match_id, session in list(session_manager._sessions.items()):
        player_ids = {p.player_id for p in session.state.players}
        if user_id in player_ids:
            try:
                async with session._lock:
                    session._event_store = EventStore(db)
                    final_scores = {k: float(v) for k, v in session.state.scores.items()}
                    game_result = GameResult(
                        winners=[],
                        final_scores=final_scores,
                        reason="admin_terminated",
                    )
                    await session._finish_game(game_result)
                session_manager.remove_session(match_id)
                state_store = session_manager._state_store
                await state_store.delete_state(match_id)
                cm = request.app.state.connection_manager
                cm.cleanup_match(match_id)
            except Exception as e:
                logger.error(f"Failed to force-finish match {match_id} during ban: {e}")

    await db.commit()
    logger.info(f"Admin banned user {user_id} ({user.display_name})")
    return {"ok": True}


@router.post("/unban/{user_id}")
async def admin_unban_user(
    user_id: str,
    current_user: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Unban a user."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(400, "Invalid user ID")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(404, "User not found")

    user.is_banned = False
    await db.commit()
    logger.info(f"Admin unbanned user {user_id} ({user.display_name})")
    return {"ok": True}
