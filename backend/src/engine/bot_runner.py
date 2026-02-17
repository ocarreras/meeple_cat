"""BotRunner — schedules and executes bot moves for game sessions."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.engine.session import GameSession

from src.engine.bot_strategy import BotStrategy, get_strategy
from src.engine.event_store import EventStore
from src.engine.models import Action, GameStatus, PlayerId

logger = logging.getLogger(__name__)

BOT_DELAY_MIN = 0.5  # seconds
BOT_DELAY_MAX = 1.5  # seconds


class BotRunner:
    """Runs bot moves for game sessions.

    After each action completes, GameSession calls
    schedule_bot_move_if_needed() to check if the next
    expected player is a bot. If so, a task is spawned
    to pick an action using the strategy matching the bot's bot_id.
    """

    def __init__(
        self,
        db_session_factory: Callable[[], "AsyncSession"],
    ) -> None:
        self._db_session_factory = db_session_factory
        self._strategies: dict[str, BotStrategy] = {}

    def schedule_bot_move_if_needed(self, session: "GameSession") -> None:
        """Check if the next expected player is a bot. If so, schedule a move."""
        if session.state.status != GameStatus.ACTIVE:
            return

        phase = session.state.current_phase
        if phase.auto_resolve:
            return
        if not phase.expected_actions:
            return

        expected_player_id = phase.expected_actions[0].player_id
        if expected_player_id is None:
            return

        # Find the player object and check if it's a bot
        for p in session.state.players:
            if p.player_id == expected_player_id and p.is_bot:
                logger.info(
                    "Scheduling bot move: player=%s phase=%s bot_id=%s",
                    p.player_id, phase.name, p.bot_id,
                )
                asyncio.create_task(
                    self._execute_bot_move(session, p.player_id)
                )
                return

    async def _execute_bot_move(
        self, session: "GameSession", player_id: PlayerId
    ) -> None:
        """Wait a short delay, pick a random valid action, submit it."""
        try:
            delay = random.uniform(BOT_DELAY_MIN, BOT_DELAY_MAX)
            await asyncio.sleep(delay)

            # Re-check state after delay
            if session.state.status != GameStatus.ACTIVE:
                return

            phase = session.state.current_phase
            if not phase.expected_actions:
                return
            if phase.expected_actions[0].player_id != player_id:
                return

            # Resolve bot_id → strategy
            bot_id = "random"
            for p in session.state.players:
                if p.player_id == player_id and p.bot_id:
                    bot_id = p.bot_id
                    break

            game_id = session.state.game_id
            cache_key = f"{bot_id}:{game_id}"
            if cache_key not in self._strategies:
                self._strategies[cache_key] = get_strategy(bot_id, game_id=game_id)
                logger.info("Created strategy %s for cache_key=%s", type(self._strategies[cache_key]).__name__, cache_key)
            strategy = self._strategies[cache_key]

            logger.info(
                "Bot %s executing %s with strategy=%s (bot_id=%s)",
                player_id, phase.name, type(strategy).__name__, bot_id,
            )
            chosen = strategy.choose_action(
                session.state.game_data, phase, player_id, session.plugin,
                players=session.state.players,
            )
            action_type = phase.expected_actions[0].action_type

            action = Action(
                action_type=action_type,
                player_id=player_id,
                payload=chosen,
            )

            # Submit through normal handle_action flow
            async with self._db_session_factory() as db_session:
                event_store = EventStore(db_session)
                session._event_store = event_store
                await session.handle_action(action)
                await db_session.commit()

            logger.info(
                f"Bot {player_id} played {action_type}: {chosen}"
            )

        except Exception as e:
            logger.error(f"Bot move failed for {player_id}: {e}", exc_info=True)
