from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import TokenData, create_token, get_current_user
from src.engine.models import GameConfig, Player, PlayerId
from src.models.database import get_db
from src.models.match import Match, MatchPlayer
from src.models.room import GameRoom, GameRoomSeat
from src.models.user import User

router = APIRouter(prefix="/rooms", tags=["rooms"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CreateRoomRequest(BaseModel):
    game_id: str
    max_players: int | None = None
    config: dict = {}


class AddBotRequest(BaseModel):
    bot_id: str = "random"


class SeatResponse(BaseModel):
    seat_index: int
    user_id: str | None
    display_name: str | None
    is_bot: bool
    bot_id: str | None
    is_ready: bool


class RoomResponse(BaseModel):
    room_id: str
    game_id: str
    created_by: str
    creator_name: str
    status: str
    max_players: int
    config: dict
    created_at: str
    seats: list[SeatResponse]
    match_id: str | None


class JoinRoomResponse(BaseModel):
    room: RoomResponse
    seat_index: int


class StartRoomResponse(BaseModel):
    match_id: str
    tokens: dict[str, str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _room_to_response(room: GameRoom) -> RoomResponse:
    return RoomResponse(
        room_id=str(room.id),
        game_id=room.game_id,
        created_by=str(room.created_by),
        creator_name=room.creator.display_name,
        status=room.status,
        max_players=room.max_players,
        config=room.config,
        created_at=room.created_at.isoformat(),
        match_id=str(room.match_id) if room.match_id else None,
        seats=[
            SeatResponse(
                seat_index=seat.seat_index,
                user_id=str(seat.user_id) if seat.user_id else None,
                display_name=seat.user.display_name if seat.user else None,
                is_bot=seat.is_bot,
                bot_id=seat.bot_id,
                is_ready=seat.is_ready,
            )
            for seat in room.seats
        ],
    )


async def _load_room(db: AsyncSession, room_id: str) -> GameRoom:
    """Load a room with seats and users eagerly loaded."""
    try:
        room_uuid = UUID(room_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Room not found")

    result = await db.execute(
        select(GameRoom)
        .where(GameRoom.id == room_uuid)
        .options(
            selectinload(GameRoom.seats).selectinload(GameRoomSeat.user),
            selectinload(GameRoom.creator),
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


def _find_user_seat(room: GameRoom, user_id: str) -> GameRoomSeat | None:
    """Find the seat occupied by a given user."""
    for seat in room.seats:
        if seat.user_id and str(seat.user_id) == user_id:
            return seat
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_rooms(
    request: Request,
    game_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[RoomResponse]:
    """List open rooms."""
    query = (
        select(GameRoom)
        .where(GameRoom.status.in_(["waiting", "starting"]))
        .options(
            selectinload(GameRoom.seats).selectinload(GameRoomSeat.user),
            selectinload(GameRoom.creator),
        )
        .order_by(GameRoom.created_at.desc())
    )
    if game_id:
        query = query.where(GameRoom.game_id == game_id)

    result = await db.execute(query)
    rooms = result.scalars().all()
    return [_room_to_response(room) for room in rooms]


@router.post("", response_model=RoomResponse)
async def create_room(
    request_body: CreateRoomRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Create a new room."""
    registry = request.app.state.registry
    try:
        plugin = registry.get(request_body.game_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Game '{request_body.game_id}' not found",
        )

    # Determine max_players
    max_players = request_body.max_players or plugin.max_players
    if max_players < plugin.min_players or max_players > plugin.max_players:
        raise HTTPException(
            status_code=400,
            detail=f"Player count must be between {plugin.min_players} and {plugin.max_players}",
        )

    # Find or create user
    result = await db.execute(
        select(User).where(User.id == UUID(current_user.user_id))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    room = GameRoom(
        game_id=request_body.game_id,
        created_by=user.id,
        config=request_body.config,
        max_players=max_players,
    )
    db.add(room)
    await db.flush()

    # Pre-create all seats (empty)
    for i in range(max_players):
        seat = GameRoomSeat(
            room_id=room.id,
            seat_index=i,
            # Seat 0 goes to the creator, auto-ready
            user_id=user.id if i == 0 else None,
            is_ready=i == 0,
        )
        db.add(seat)

    await db.flush()

    # Reload with relationships
    room = await _load_room(db, str(room.id))
    return _room_to_response(room)


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Get room details."""
    room = await _load_room(db, room_id)
    return _room_to_response(room)


@router.post("/{room_id}/join", response_model=JoinRoomResponse)
async def join_room(
    room_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JoinRoomResponse:
    """Join a room."""
    room = await _load_room(db, room_id)

    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Room is not accepting players")

    # Check if user is already in the room
    existing = _find_user_seat(room, current_user.user_id)
    if existing:
        raise HTTPException(status_code=400, detail="Already in this room")

    # Find first empty seat
    empty_seat = None
    for seat in room.seats:
        if seat.user_id is None and not seat.is_bot:
            empty_seat = seat
            break

    if empty_seat is None:
        raise HTTPException(status_code=400, detail="Room is full")

    empty_seat.user_id = UUID(current_user.user_id)
    empty_seat.is_ready = False
    await db.flush()

    # Reload
    room = await _load_room(db, room_id)
    return JoinRoomResponse(
        room=_room_to_response(room),
        seat_index=empty_seat.seat_index,
    )


@router.post("/{room_id}/leave")
async def leave_room(
    room_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Leave a room."""
    room = await _load_room(db, room_id)

    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Cannot leave a room that has started")

    seat = _find_user_seat(room, current_user.user_id)
    if not seat:
        raise HTTPException(status_code=400, detail="Not in this room")

    if str(room.created_by) == current_user.user_id:
        # Creator leaving deletes the room
        await db.delete(room)
    else:
        seat.user_id = None
        seat.is_ready = False

    return {"ok": True}


@router.post("/{room_id}/ready", response_model=RoomResponse)
async def toggle_ready(
    room_id: str,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Toggle ready status."""
    room = await _load_room(db, room_id)

    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Room is not in waiting state")

    seat = _find_user_seat(room, current_user.user_id)
    if not seat:
        raise HTTPException(status_code=400, detail="Not in this room")

    seat.is_ready = not seat.is_ready
    await db.flush()

    room = await _load_room(db, room_id)
    return _room_to_response(room)


@router.post("/{room_id}/add-bot", response_model=RoomResponse)
async def add_bot(
    room_id: str,
    request_body: AddBotRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomResponse:
    """Add a bot to the room."""
    room = await _load_room(db, room_id)

    if str(room.created_by) != current_user.user_id:
        raise HTTPException(status_code=403, detail="Only the room creator can add bots")

    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Room is not in waiting state")

    # Find first empty seat
    empty_seat = None
    for seat in room.seats:
        if seat.user_id is None and not seat.is_bot:
            empty_seat = seat
            break

    if empty_seat is None:
        raise HTTPException(status_code=400, detail="Room is full")

    empty_seat.is_bot = True
    empty_seat.bot_id = request_body.bot_id
    empty_seat.is_ready = True
    await db.flush()

    room = await _load_room(db, room_id)
    return _room_to_response(room)


@router.post("/{room_id}/start", response_model=StartRoomResponse)
async def start_room(
    room_id: str,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StartRoomResponse:
    """Start the game from a room."""
    room = await _load_room(db, room_id)

    # Validate creator
    if str(room.created_by) != current_user.user_id:
        raise HTTPException(status_code=403, detail="Only the room creator can start the game")

    if room.status != "waiting":
        raise HTTPException(status_code=400, detail="Room is not in waiting state")

    # Collect occupied seats
    occupied = [s for s in room.seats if s.user_id is not None or s.is_bot]
    if not occupied:
        raise HTTPException(status_code=400, detail="No players in room")

    # Validate player count
    registry = request.app.state.registry
    plugin = registry.get(room.game_id)
    if len(occupied) < plugin.min_players:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {plugin.min_players} players to start",
        )

    # Validate all occupied seats are ready
    for seat in occupied:
        if not seat.is_ready:
            display = seat.user.display_name if seat.user else f"Seat {seat.seat_index}"
            raise HTTPException(
                status_code=400,
                detail=f"{display} is not ready",
            )

    # Transition room to starting
    room.status = "starting"
    await db.flush()

    # Create bot user records for bot seats
    bot_users: dict[int, User] = {}
    for seat in occupied:
        if seat.is_bot:
            bot_name = f"Bot ({seat.bot_id})"
            result = await db.execute(
                select(User).where(User.display_name == bot_name)
            )
            bot_user = result.scalar_one_or_none()
            if not bot_user:
                bot_user = User(display_name=bot_name)
                db.add(bot_user)
                await db.flush()
            bot_users[seat.seat_index] = bot_user

    # Create Match record
    match = Match(game_id=room.game_id, status="active")
    db.add(match)
    await db.flush()

    # Create MatchPlayer records
    match_players = []
    for seat in sorted(occupied, key=lambda s: s.seat_index):
        if seat.is_bot:
            user = bot_users[seat.seat_index]
        else:
            user = seat.user

        mp = MatchPlayer(
            match_id=match.id,
            user_id=user.id,
            seat_index=seat.seat_index,
            is_bot=seat.is_bot,
            bot_id=seat.bot_id,
        )
        db.add(mp)
        match_players.append((mp, user))

    await db.commit()

    # Build Player objects for game session
    players = [
        Player(
            player_id=PlayerId(str(user.id)),
            display_name=user.display_name,
            seat_index=mp.seat_index,
            is_bot=mp.is_bot,
            bot_id=mp.bot_id,
        )
        for mp, user in match_players
    ]

    config = GameConfig(options=room.config)

    # Create game session
    session_manager = request.app.state.session_manager
    await session_manager.create_session(
        match_id=str(match.id),
        game_id=room.game_id,
        players=players,
        config=config,
    )

    # Update room
    room.status = "in_game"
    room.match_id = match.id
    await db.commit()

    # Generate tokens for all human players
    tokens: dict[str, str] = {}
    for mp, user in match_players:
        if not mp.is_bot:
            tokens[str(user.id)] = create_token(str(user.id), user.display_name)

    return StartRoomResponse(
        match_id=str(match.id),
        tokens=tokens,
    )
