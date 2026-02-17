//! TicTacToe game plugin — minimal game for MCTS algorithm validation.
//!
//! Used to isolate MCTS core correctness from Carcassonne-specific game logic.
//! TicTacToe is deterministic with a tiny search space, so MCTS should play
//! near-perfectly even with modest simulation counts.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

use crate::engine::models::*;
use crate::engine::plugin::{TypedGamePlugin, TypedTransitionResult};

const WIN_LINES: [[usize; 3]; 8] = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8], // rows
    [0, 3, 6], [1, 4, 7], [2, 5, 8], // cols
    [0, 4, 8], [2, 4, 6],             // diagonals
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TicTacToeState {
    /// 9 cells: None=empty, Some(0)=X (player 0), Some(1)=O (player 1)
    pub board: [Option<u8>; 9],
    /// Index into players array (0 or 1)
    pub current_player: usize,
    pub scores: HashMap<String, f64>,
}

fn check_winner(board: &[Option<u8>; 9]) -> Option<u8> {
    for line in &WIN_LINES {
        let a = board[line[0]];
        if a.is_some() && a == board[line[1]] && a == board[line[2]] {
            return a;
        }
    }
    None
}

fn is_draw(board: &[Option<u8>; 9]) -> bool {
    board.iter().all(|c| c.is_some())
}

fn make_phase(player_id: &str) -> Phase {
    Phase {
        name: "play".into(),
        concurrent_mode: None,
        expected_actions: vec![ExpectedAction {
            player_id: player_id.into(),
            action_type: "play".into(),
            constraints: HashMap::new(),
            timeout_ms: None,
        }],
        auto_resolve: false,
        metadata: serde_json::json!({}),
    }
}

pub struct TicTacToePlugin;

impl TypedGamePlugin for TicTacToePlugin {
    type State = TicTacToeState;

    fn game_id(&self) -> &str { "tictactoe" }
    fn display_name(&self) -> &str { "Tic-Tac-Toe" }
    fn min_players(&self) -> u32 { 2 }
    fn max_players(&self) -> u32 { 2 }
    fn description(&self) -> &str { "Classic 3x3 Tic-Tac-Toe" }
    fn disconnect_policy(&self) -> &str { "abandon_all" }

    fn decode_state(&self, game_data: &serde_json::Value) -> TicTacToeState {
        serde_json::from_value(game_data.clone()).expect("invalid TicTacToeState JSON")
    }

    fn encode_state(&self, state: &TicTacToeState) -> serde_json::Value {
        serde_json::to_value(state).expect("failed to encode TicTacToeState")
    }

    fn create_initial_state(
        &self,
        players: &[Player],
        _config: &GameConfig,
    ) -> (TicTacToeState, Phase, Vec<Event>) {
        let mut scores = HashMap::new();
        for p in players {
            scores.insert(p.player_id.clone(), 0.0);
        }
        let state = TicTacToeState {
            board: [None; 9],
            current_player: 0,
            scores,
        };
        let phase = make_phase(&players[0].player_id);
        (state, phase, vec![])
    }

    fn get_valid_actions(
        &self,
        state: &TicTacToeState,
        _phase: &Phase,
        _player_id: &str,
    ) -> Vec<serde_json::Value> {
        state.board.iter().enumerate()
            .filter(|(_, cell)| cell.is_none())
            .map(|(i, _)| serde_json::json!({"cell": i}))
            .collect()
    }

    fn validate_action(
        &self,
        state: &TicTacToeState,
        _phase: &Phase,
        action: &Action,
    ) -> Option<String> {
        let cell = match action.payload.get("cell").and_then(|v| v.as_u64()) {
            Some(c) if c < 9 => c as usize,
            _ => return Some("invalid cell".into()),
        };
        if state.board[cell].is_some() {
            return Some("cell already occupied".into());
        }
        None
    }

    fn apply_action(
        &self,
        state: &TicTacToeState,
        _phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TypedTransitionResult<TicTacToeState> {
        let cell = action.payload.get("cell")
            .and_then(|v| v.as_u64())
            .expect("action must have cell") as usize;

        let mut new_state = state.clone();
        new_state.board[cell] = Some(state.current_player as u8);

        // Check for winner
        if let Some(winner_mark) = check_winner(&new_state.board) {
            let winner_idx = winner_mark as usize;
            let loser_idx = 1 - winner_idx;
            let winner_pid = &players[winner_idx].player_id;
            let loser_pid = &players[loser_idx].player_id;

            new_state.scores.insert(winner_pid.clone(), 1.0);
            new_state.scores.insert(loser_pid.clone(), 0.0);

            return TypedTransitionResult {
                scores: new_state.scores.clone(),
                game_over: Some(GameResult {
                    winners: vec![winner_pid.clone()],
                    final_scores: new_state.scores.clone(),
                    reason: "normal".into(),
                    details: HashMap::new(),
                }),
                next_phase: make_phase(winner_pid), // doesn't matter, game is over
                state: new_state,
                events: vec![],
            };
        }

        // Check for draw
        if is_draw(&new_state.board) {
            new_state.scores.insert(players[0].player_id.clone(), 0.5);
            new_state.scores.insert(players[1].player_id.clone(), 0.5);

            return TypedTransitionResult {
                scores: new_state.scores.clone(),
                game_over: Some(GameResult {
                    winners: vec![players[0].player_id.clone(), players[1].player_id.clone()],
                    final_scores: new_state.scores.clone(),
                    reason: "draw".into(),
                    details: HashMap::new(),
                }),
                next_phase: make_phase(&players[0].player_id),
                state: new_state,
                events: vec![],
            };
        }

        // Continue: switch player
        let next_player = 1 - state.current_player;
        new_state.current_player = next_player;

        TypedTransitionResult {
            scores: new_state.scores.clone(),
            game_over: None,
            next_phase: make_phase(&players[next_player].player_id),
            state: new_state,
            events: vec![],
        }
    }

    fn get_player_view(
        &self,
        state: &TicTacToeState,
        _phase: &Phase,
        _player_id: Option<&str>,
        _players: &[Player],
    ) -> serde_json::Value {
        self.encode_state(state)
    }

    fn get_scores(&self, state: &TicTacToeState) -> HashMap<String, f64> {
        state.scores.clone()
    }

    fn parse_ai_action(
        &self,
        response: &serde_json::Value,
        _phase: &Phase,
        player_id: &str,
    ) -> Action {
        Action {
            action_type: "play".into(),
            player_id: player_id.into(),
            payload: response.clone(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::mcts::{mcts_search, MctsParams};
    use crate::engine::bot_strategy::{BotStrategy, RandomStrategy};
    use crate::engine::arena::run_arena;

    fn make_players() -> Vec<Player> {
        vec![
            Player { player_id: "p0".into(), display_name: "X".into(), seat_index: 0, is_bot: true, bot_id: None },
            Player { player_id: "p1".into(), display_name: "O".into(), seat_index: 1, is_bot: true, bot_id: None },
        ]
    }

    #[test]
    fn test_game_flow() {
        let plugin = TicTacToePlugin;
        let players = make_players();
        let config = GameConfig { random_seed: Some(42), options: serde_json::json!({}) };
        let (state, phase, _) = plugin.create_initial_state(&players, &config);

        assert_eq!(state.current_player, 0);
        assert_eq!(plugin.get_valid_actions(&state, &phase, "p0").len(), 9);

        // p0 plays center
        let action = Action { action_type: "play".into(), player_id: "p0".into(), payload: serde_json::json!({"cell": 4}) };
        let result = plugin.apply_action(&state, &phase, &action, &players);
        assert!(result.game_over.is_none());
        assert_eq!(result.state.board[4], Some(0));
        assert_eq!(result.state.current_player, 1);
    }

    #[test]
    fn test_win_detection() {
        let plugin = TicTacToePlugin;
        let players = make_players();
        let mut scores = HashMap::new();
        scores.insert("p0".into(), 0.0);
        scores.insert("p1".into(), 0.0);

        // Set up a state where p0 has two in a row and can win
        let state = TicTacToeState {
            board: [Some(0), Some(0), None, Some(1), Some(1), None, None, None, None],
            current_player: 0,
            scores,
        };
        let phase = make_phase("p0");
        let action = Action { action_type: "play".into(), player_id: "p0".into(), payload: serde_json::json!({"cell": 2}) };
        let result = plugin.apply_action(&state, &phase, &action, &players);
        assert!(result.game_over.is_some());
        let gr = result.game_over.unwrap();
        assert_eq!(gr.winners, vec!["p0".to_string()]);
    }

    #[test]
    fn test_mcts_beats_random() {
        let plugin = TicTacToePlugin;
        let params = MctsParams {
            num_simulations: 200,
            time_limit_ms: 999999.0,
            num_determinizations: 1,
            ..Default::default()
        };

        let mut strategies: HashMap<String, Box<dyn BotStrategy<TicTacToePlugin>>> = HashMap::new();
        strategies.insert("mcts".into(), Box::new(
            crate::engine::bot_strategy::MctsStrategy::<TicTacToePlugin> {
                params,
                eval_fn: None,
            }
        ));
        strategies.insert("random".into(), Box::new(RandomStrategy));

        let result = run_arena(
            &plugin,
            &strategies,
            20,
            42,
            2,
            None,
            true,
            None,
        );

        let mcts_wins = *result.wins.get("mcts").unwrap_or(&0);
        let random_wins = *result.wins.get("random").unwrap_or(&0);
        eprintln!("MCTS vs Random (20 games): mcts={} random={} draws={}", mcts_wins, random_wins, result.draws);
        assert!(mcts_wins >= 15, "MCTS should win most games vs random, got {}", mcts_wins);
    }
}
