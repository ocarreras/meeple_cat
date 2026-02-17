"""TicTacToe game plugin — minimal game for MCTS algorithm validation.

Used to isolate MCTS core correctness from Carcassonne-specific game logic.
"""

from __future__ import annotations

from src.engine.models import (
    Action,
    Event,
    ExpectedAction,
    GameConfig,
    GameResult,
    Phase,
    Player,
    PlayerId,
    TransitionResult,
)

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # cols
    (0, 4, 8), (2, 4, 6),              # diagonals
]


def _check_winner(board: list) -> int | None:
    for a, b, c in WIN_LINES:
        if board[a] is not None and board[a] == board[b] == board[c]:
            return board[a]
    return None


def _is_draw(board: list) -> bool:
    return all(cell is not None for cell in board)


def _make_phase(player_id: str) -> Phase:
    return Phase(
        name="play",
        expected_actions=[
            ExpectedAction(player_id=PlayerId(player_id), action_type="play")
        ],
    )


class TicTacToePlugin:
    game_id = "tictactoe"
    display_name = "Tic-Tac-Toe"
    min_players = 2
    max_players = 2
    description = "Classic 3x3 Tic-Tac-Toe"
    config_schema = {}
    disconnect_policy = "abandon_all"

    def create_initial_state(
        self, players: list[Player], config: GameConfig
    ) -> tuple[dict, Phase, list[Event]]:
        scores = {p.player_id: 0.0 for p in players}
        game_data = {
            "board": [None] * 9,
            "current_player": 0,
            "scores": scores,
        }
        phase = _make_phase(players[0].player_id)
        return game_data, phase, []

    def validate_config(self, options: dict) -> list[str]:
        return []

    def get_valid_actions(
        self, game_data: dict, phase: Phase, player_id: PlayerId
    ) -> list[dict]:
        board = game_data["board"]
        return [{"cell": i} for i, cell in enumerate(board) if cell is None]

    def validate_action(
        self, game_data: dict, phase: Phase, action: Action
    ) -> str | None:
        cell = action.payload.get("cell")
        if cell is None or not (0 <= cell < 9):
            return "invalid cell"
        if game_data["board"][cell] is not None:
            return "cell already occupied"
        return None

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        cell = action.payload["cell"]
        current = game_data["current_player"]

        board = list(game_data["board"])
        board[cell] = current
        scores = dict(game_data["scores"])

        # Check winner
        winner_mark = _check_winner(board)
        if winner_mark is not None:
            winner_idx = winner_mark
            loser_idx = 1 - winner_idx
            winner_pid = players[winner_idx].player_id
            loser_pid = players[loser_idx].player_id
            scores[winner_pid] = 1.0
            scores[loser_pid] = 0.0

            new_data = {"board": board, "current_player": current, "scores": scores}
            return TransitionResult(
                game_data=new_data,
                events=[],
                next_phase=_make_phase(winner_pid),
                scores=scores,
                game_over=GameResult(
                    winners=[winner_pid],
                    final_scores=scores,
                    reason="normal",
                ),
            )

        # Check draw
        if _is_draw(board):
            scores[players[0].player_id] = 0.5
            scores[players[1].player_id] = 0.5

            new_data = {"board": board, "current_player": current, "scores": scores}
            return TransitionResult(
                game_data=new_data,
                events=[],
                next_phase=_make_phase(players[0].player_id),
                scores=scores,
                game_over=GameResult(
                    winners=[players[0].player_id, players[1].player_id],
                    final_scores=scores,
                    reason="draw",
                ),
            )

        # Continue: switch player
        next_player = 1 - current
        new_data = {"board": board, "current_player": next_player, "scores": scores}
        return TransitionResult(
            game_data=new_data,
            events=[],
            next_phase=_make_phase(players[next_player].player_id),
            scores=scores,
        )

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,
        players: list[Player],
    ) -> dict:
        return game_data

    def resolve_concurrent_actions(self, game_data, phase, actions, players):
        raise NotImplementedError

    def state_to_ai_view(self, game_data, phase, player_id, players):
        return game_data

    def parse_ai_action(self, response, phase, player_id):
        return Action(action_type="play", player_id=player_id, payload=response)

    def on_player_forfeit(self, game_data, phase, player_id, players):
        return None

    def get_spectator_summary(self, game_data, phase, players):
        return game_data
