from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import TokenData, get_current_user
from src.engine.models import GameConfig, Player, PlayerId
from src.models.database import get_db
from src.models.match import Match, MatchPlayer
from src.models.user import User

router = APIRouter(prefix="/matches", tags=["matches"])


class CreateMatchRequest(BaseModel):
    game_id: str
    player_display_names: list[str]
    config: dict = {}
    random_seed: int | None = None
    bot_seats: list[int] = []
    bot_id: str = "random"


class MatchResponse(BaseModel):
    match_id: str
    game_id: str
    status: str
    players: list[dict]


@router.post("", response_model=MatchResponse)
async def create_match(
    request_body: CreateMatchRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Create a new match."""
    # Validate game exists
    registry = request.app.state.registry
    try:
        plugin = registry.get(request_body.game_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Game '{request_body.game_id}' not found")

    # Validate player count
    player_count = len(request_body.player_display_names)
    if player_count < plugin.min_players or player_count > plugin.max_players:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid player count: {player_count}. Must be between {plugin.min_players} and {plugin.max_players}",
        )

    # Validate bot_seats are valid indices
    bot_seats = set(request_body.bot_seats)
    for seat in bot_seats:
        if seat < 0 or seat >= player_count:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid bot seat index: {seat}",
            )

    # Validate creator is a non-bot player
    non_bot_names = [
        name for i, name in enumerate(request_body.player_display_names)
        if i not in bot_seats
    ]
    if current_user.display_name not in non_bot_names:
        raise HTTPException(
            status_code=400,
            detail="Creator must be a non-bot player",
        )

    # Find or create users for all players
    users: dict[str, User] = {}
    for display_name in request_body.player_display_names:
        result = await db.execute(select(User).where(User.display_name == display_name))
        user = result.scalar_one_or_none()
        if not user:
            user = User(display_name=display_name)
            db.add(user)
            await db.flush()  # Flush to get the ID
        users[display_name] = user

    # Create Match record
    match = Match(game_id=request_body.game_id, status="active")
    db.add(match)
    await db.flush()  # Get match ID

    # Create MatchPlayer records
    match_players = []
    for seat_index, display_name in enumerate(request_body.player_display_names):
        user = users[display_name]
        is_bot = seat_index in bot_seats
        match_player = MatchPlayer(
            match_id=match.id,
            user_id=user.id,
            seat_index=seat_index,
            is_bot=is_bot,
            bot_id=request_body.bot_id if is_bot else None,
        )
        db.add(match_player)
        match_players.append(match_player)

    await db.commit()  # Commit so game_events FK can reference this match

    # Build Player objects for game session
    players = [
        Player(
            player_id=PlayerId(str(mp.user_id)),
            display_name=users[request_body.player_display_names[mp.seat_index]].display_name,
            seat_index=mp.seat_index,
            is_bot=mp.is_bot,
            bot_id=mp.bot_id,
        )
        for mp in match_players
    ]

    # Build config
    config = GameConfig(
        options=request_body.config,
        random_seed=request_body.random_seed,
    )

    # Create game session
    session_manager = request.app.state.session_manager
    await session_manager.create_session(
        match_id=str(match.id),
        game_id=request_body.game_id,
        players=players,
        config=config,
    )

    return MatchResponse(
        match_id=str(match.id),
        game_id=match.game_id,
        status=match.status,
        players=[
            {
                "user_id": str(mp.user_id),
                "display_name": users[request_body.player_display_names[mp.seat_index]].display_name,
                "seat_index": mp.seat_index,
                "is_bot": mp.is_bot,
            }
            for mp in match_players
        ],
    )


@router.get("/{match_id}", response_model=MatchResponse)
async def get_match(
    match_id: str,
    db: AsyncSession = Depends(get_db),
) -> MatchResponse:
    """Get match details."""
    try:
        match_uuid = UUID(match_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Match not found")

    result = await db.execute(
        select(Match)
        .where(Match.id == match_uuid)
        .options(selectinload(Match.players).selectinload(MatchPlayer.user))
    )
    match = result.scalar_one_or_none()

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    return MatchResponse(
        match_id=str(match.id),
        game_id=match.game_id,
        status=match.status,
        players=[
            {
                "user_id": str(mp.user_id),
                "display_name": mp.user.display_name,
                "seat_index": mp.seat_index,
                "is_bot": mp.is_bot,
            }
            for mp in sorted(match.players, key=lambda x: x.seat_index)
        ],
    )
