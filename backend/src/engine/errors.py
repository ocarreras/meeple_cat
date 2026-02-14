from __future__ import annotations

from src.engine.models import Action


class GameEngineError(Exception):
    """Base class for engine errors."""
    pass


class InvalidActionError(GameEngineError):
    """Action is not valid in current state."""

    def __init__(self, message: str, action: Action | None = None):
        self.message = message
        self.action = action
        super().__init__(message)


class GameNotActiveError(GameEngineError):
    """Action submitted to a non-active game."""
    pass


class NotYourTurnError(GameEngineError):
    """Player tried to act when it's not their turn."""
    pass


class PluginError(GameEngineError):
    """Game plugin raised an unexpected error."""

    def __init__(self, message: str, original: Exception | None = None):
        self.message = message
        self.original = original
        super().__init__(message)
