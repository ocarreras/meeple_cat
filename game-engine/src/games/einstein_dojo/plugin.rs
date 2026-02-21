//! EinsteinDojoPlugin — implements TypedGamePlugin trait.

use std::collections::HashMap;

use crate::engine::models::*;
use crate::engine::plugin::{TypedGamePlugin, TypedTransitionResult};

use super::board::{apply_placement, get_all_valid_placements, validate_placement};
use super::scoring::count_complete_hexes;
use super::types::*;

const TILES_PER_PLAYER: i32 = 16;

pub struct EinsteinDojoPlugin;

impl TypedGamePlugin for EinsteinDojoPlugin {
    type State = EinsteinDojoState;

    fn game_id(&self) -> &str {
        "einstein_dojo"
    }
    fn display_name(&self) -> &str {
        "Ein Stein Dojo"
    }
    fn min_players(&self) -> u32 {
        2
    }
    fn max_players(&self) -> u32 {
        2
    }
    fn description(&self) -> &str {
        "Place Einstein hat tiles on a hexagonal board to complete hexagons. \
         A 2-player abstract strategy game."
    }
    fn disconnect_policy(&self) -> &str {
        "forfeit_player"
    }

    fn decode_state(&self, game_data: &serde_json::Value) -> EinsteinDojoState {
        serde_json::from_value(game_data.clone())
            .unwrap_or_else(|e| panic!("Failed to decode EinsteinDojoState: {e}"))
    }

    fn encode_state(&self, state: &EinsteinDojoState) -> serde_json::Value {
        serde_json::to_value(state).expect("serialization should not fail")
    }

    fn create_initial_state(
        &self,
        players: &[Player],
        _config: &GameConfig,
    ) -> (EinsteinDojoState, Phase, Vec<Event>) {
        let tiles_remaining: HashMap<String, i32> = players
            .iter()
            .map(|p| (p.player_id.clone(), TILES_PER_PLAYER))
            .collect();
        let scores: HashMap<String, i64> =
            players.iter().map(|p| (p.player_id.clone(), 0)).collect();

        let state = EinsteinDojoState {
            board: Board::new(),
            tiles_remaining,
            scores,
            current_player_index: 0,
            main_conflict: None,
        };

        let first_player = &players[0];
        let phase = Phase {
            name: "place_tile".into(),
            concurrent_mode: Some(ConcurrentMode::Sequential),
            expected_actions: vec![ExpectedAction {
                player_id: first_player.player_id.clone(),
                action_type: "place_tile".into(),
                constraints: HashMap::new(),
                timeout_ms: None,
            }],
            auto_resolve: false,
            metadata: serde_json::json!({"player_index": 0}),
        };

        let events = vec![Event {
            event_type: "game_started".into(),
            player_id: None,
            payload: serde_json::json!({
                "players": players.iter().map(|p| &p.player_id).collect::<Vec<_>>(),
                "tiles_per_player": TILES_PER_PLAYER,
            }),
        }];

        (state, phase, events)
    }

    fn get_valid_actions(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value> {
        let expected_pid = phase
            .expected_actions
            .first()
            .map(|ea| ea.player_id.as_str());
        if expected_pid != Some(player_id) {
            return vec![];
        }

        match phase.name.as_str() {
            "place_tile" => {
                if state.tiles_remaining.get(player_id).copied().unwrap_or(0) <= 0 {
                    return vec![];
                }
                get_all_valid_placements(&state.board)
                    .into_iter()
                    .map(|(orientation, anchor_q, anchor_r)| {
                        serde_json::json!({
                            "anchor_q": anchor_q,
                            "anchor_r": anchor_r,
                            "orientation": orientation,
                        })
                    })
                    .collect()
            }
            "choose_main_conflict" => {
                phase.metadata.get("conflict_hexes")
                    .and_then(|v| v.as_array())
                    .map(|hexes| {
                        hexes.iter()
                            .map(|h| serde_json::json!({"hex": h}))
                            .collect()
                    })
                    .unwrap_or_default()
            }
            _ => vec![],
        }
    }

    fn validate_action(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        action: &Action,
    ) -> Option<String> {
        match phase.name.as_str() {
            "place_tile" => self.validate_place_tile(state, action),
            "choose_main_conflict" => self.validate_choose_main_conflict(phase, action),
            _ => None,
        }
    }

    fn apply_action(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TypedTransitionResult<EinsteinDojoState> {
        match phase.name.as_str() {
            "place_tile" => self.apply_place_tile(state, phase, action, players),
            "score_check" => self.apply_score_check(state, phase, players),
            "choose_main_conflict" => self.apply_choose_main_conflict(state, phase, action),
            _ => panic!("Unknown phase: {}", phase.name),
        }
    }

    fn get_player_view(
        &self,
        state: &EinsteinDojoState,
        _phase: &Phase,
        _player_id: Option<&str>,
        _players: &[Player],
    ) -> serde_json::Value {
        // No hidden information — return full state
        self.encode_state(state)
    }

    fn get_scores(&self, state: &EinsteinDojoState) -> HashMap<String, f64> {
        state.float_scores()
    }

    fn parse_ai_action(
        &self,
        response: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Action {
        let action_type = if !phase.expected_actions.is_empty() {
            phase.expected_actions[0].action_type.clone()
        } else {
            phase.name.clone()
        };
        let payload = response
            .get("action")
            .and_then(|a| a.get("payload"))
            .unwrap_or(response)
            .clone();
        Action {
            action_type,
            player_id: player_id.into(),
            payload,
        }
    }

    fn on_player_forfeit(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> Option<TypedTransitionResult<EinsteinDojoState>> {
        match phase.name.as_str() {
            "place_tile" => {
                let current_idx = phase.metadata["player_index"].as_u64()? as usize;
                let mut s = state.clone();

                let next_idx = (current_idx + 1) % players.len();
                let next_player = &players[next_idx];
                s.current_player_index = next_idx;

                Some(TypedTransitionResult {
                    state: s.clone(),
                    events: vec![Event {
                        event_type: "turn_skipped".into(),
                        player_id: Some(player_id.into()),
                        payload: serde_json::json!({}),
                    }],
                    next_phase: make_place_tile_phase(next_idx, &next_player.player_id),
                    scores: s.float_scores(),
                    game_over: None,
                })
            }
            "choose_main_conflict" => {
                // Auto-pick first conflict hex on forfeit
                let mut s = state.clone();
                let conflict_hexes = phase.metadata.get("conflict_hexes")
                    .and_then(|v| v.as_array())
                    .and_then(|arr| arr.first())
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string());
                s.main_conflict = conflict_hexes;

                let player_index = phase.metadata["player_index"].as_u64()? as usize;

                Some(TypedTransitionResult {
                    state: s.clone(),
                    events: vec![Event {
                        event_type: "main_conflict_chosen".into(),
                        player_id: Some(player_id.into()),
                        payload: serde_json::json!({"hex": s.main_conflict, "forfeited": true}),
                    }],
                    next_phase: Phase {
                        name: "score_check".into(),
                        auto_resolve: true,
                        concurrent_mode: None,
                        expected_actions: vec![],
                        metadata: serde_json::json!({"player_index": player_index}),
                    },
                    scores: s.float_scores(),
                    game_over: None,
                })
            }
            _ => None,
        }
    }
}

// ── Private helpers ──

impl EinsteinDojoPlugin {
    fn validate_place_tile(
        &self,
        state: &EinsteinDojoState,
        action: &Action,
    ) -> Option<String> {
        let orientation = action
            .payload
            .get("orientation")
            .and_then(|v| v.as_u64())
            .map(|v| v as u8);
        let anchor_q = action
            .payload
            .get("anchor_q")
            .and_then(|v| v.as_i64())
            .map(|v| v as i32);
        let anchor_r = action
            .payload
            .get("anchor_r")
            .and_then(|v| v.as_i64())
            .map(|v| v as i32);

        match (orientation, anchor_q, anchor_r) {
            (Some(o), Some(aq), Some(ar)) => {
                if state
                    .tiles_remaining
                    .get(&action.player_id)
                    .copied()
                    .unwrap_or(0)
                    <= 0
                {
                    return Some("No tiles remaining".into());
                }
                validate_placement(&state.board, o, aq, ar)
            }
            _ => Some("Missing orientation, anchor_q, or anchor_r in payload".into()),
        }
    }

    fn apply_place_tile(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        action: &Action,
        _players: &[Player],
    ) -> TypedTransitionResult<EinsteinDojoState> {
        let mut s = state.clone();
        let player_id = &action.player_id;
        let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;

        let orientation = action.payload["orientation"].as_u64().unwrap() as u8;
        let anchor_q = action.payload["anchor_q"].as_i64().unwrap() as i32;
        let anchor_r = action.payload["anchor_r"].as_i64().unwrap() as i32;

        let changed_hexes = apply_placement(&mut s.board, player_id, orientation, anchor_q, anchor_r);

        // Decrement tile count
        if let Some(remaining) = s.tiles_remaining.get_mut(player_id) {
            *remaining -= 1;
        }

        let events = vec![Event {
            event_type: "tile_placed".into(),
            player_id: Some(player_id.clone()),
            payload: serde_json::json!({
                "anchor_q": anchor_q,
                "anchor_r": anchor_r,
                "orientation": orientation,
                "changed_hexes": &changed_hexes,
            }),
        }];

        let score_check_phase = Phase {
            name: "score_check".into(),
            auto_resolve: true,
            concurrent_mode: None,
            expected_actions: vec![],
            metadata: serde_json::json!({"player_index": player_index}),
        };

        // Detect new conflicts and potentially trigger choose_main_conflict
        if s.main_conflict.is_none() {
            let new_conflicts: Vec<String> = changed_hexes
                .iter()
                .filter(|hex_key| {
                    s.board.hex_states.get(*hex_key).copied() == Some(HexState::Conflict)
                })
                .cloned()
                .collect();

            if new_conflicts.len() == 1 {
                // Auto-set the single new conflict as main
                s.main_conflict = Some(new_conflicts[0].clone());
                return TypedTransitionResult {
                    state: s.clone(),
                    events,
                    next_phase: score_check_phase,
                    scores: s.float_scores(),
                    game_over: None,
                };
            } else if new_conflicts.len() > 1 {
                // Player must choose which conflict is the main one
                return TypedTransitionResult {
                    state: s.clone(),
                    events,
                    next_phase: Phase {
                        name: "choose_main_conflict".into(),
                        auto_resolve: false,
                        concurrent_mode: Some(ConcurrentMode::Sequential),
                        expected_actions: vec![ExpectedAction {
                            player_id: player_id.clone(),
                            action_type: "choose_main_conflict".into(),
                            constraints: HashMap::new(),
                            timeout_ms: None,
                        }],
                        metadata: serde_json::json!({
                            "player_index": player_index,
                            "conflict_hexes": new_conflicts,
                        }),
                    },
                    scores: s.float_scores(),
                    game_over: None,
                };
            }
        }

        // No main conflict logic needed — proceed to score_check
        TypedTransitionResult {
            state: s.clone(),
            events,
            next_phase: score_check_phase,
            scores: s.float_scores(),
            game_over: None,
        }
    }

    fn apply_score_check(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        players: &[Player],
    ) -> TypedTransitionResult<EinsteinDojoState> {
        let mut s = state.clone();
        let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
        let current_player = &players[player_index];

        // Recount complete hexes for all players
        let complete_counts = count_complete_hexes(&s.board);
        for p in players {
            s.scores.insert(
                p.player_id.clone(),
                complete_counts.get(&p.player_id).copied().unwrap_or(0),
            );
        }

        // Check game end: current player used their last tile
        let tiles_left = s
            .tiles_remaining
            .get(&current_player.player_id)
            .copied()
            .unwrap_or(0);

        if tiles_left <= 0 {
            return self.end_game(s, players);
        }

        // Advance to next player
        let next_idx = (player_index + 1) % players.len();
        let next_player = &players[next_idx];
        s.current_player_index = next_idx;

        TypedTransitionResult {
            state: s.clone(),
            events: vec![],
            next_phase: make_place_tile_phase(next_idx, &next_player.player_id),
            scores: s.float_scores(),
            game_over: None,
        }
    }

    fn validate_choose_main_conflict(
        &self,
        phase: &Phase,
        action: &Action,
    ) -> Option<String> {
        let hex = action.payload.get("hex").and_then(|v| v.as_str());
        match hex {
            None => Some("Missing 'hex' in payload".into()),
            Some(chosen) => {
                let allowed = phase.metadata.get("conflict_hexes")
                    .and_then(|v| v.as_array())
                    .map(|arr| arr.iter().any(|h| h.as_str() == Some(chosen)))
                    .unwrap_or(false);
                if !allowed {
                    Some(format!("Hex {chosen} is not a valid conflict choice"))
                } else {
                    None
                }
            }
        }
    }

    fn apply_choose_main_conflict(
        &self,
        state: &EinsteinDojoState,
        phase: &Phase,
        action: &Action,
    ) -> TypedTransitionResult<EinsteinDojoState> {
        let mut s = state.clone();
        let chosen_hex = action.payload["hex"].as_str().unwrap().to_string();
        s.main_conflict = Some(chosen_hex.clone());

        let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;

        TypedTransitionResult {
            state: s.clone(),
            events: vec![Event {
                event_type: "main_conflict_chosen".into(),
                player_id: Some(action.player_id.clone()),
                payload: serde_json::json!({"hex": chosen_hex}),
            }],
            next_phase: Phase {
                name: "score_check".into(),
                auto_resolve: true,
                concurrent_mode: None,
                expected_actions: vec![],
                metadata: serde_json::json!({"player_index": player_index}),
            },
            scores: s.float_scores(),
            game_over: None,
        }
    }

    fn end_game(
        &self,
        state: EinsteinDojoState,
        players: &[Player],
    ) -> TypedTransitionResult<EinsteinDojoState> {
        let final_scores = state.float_scores();
        let max_score = state.scores.values().copied().max().unwrap_or(0);

        let players_with_max: Vec<&Player> = players
            .iter()
            .filter(|p| state.scores.get(&p.player_id).copied().unwrap_or(0) == max_score)
            .collect();

        let winners = if players_with_max.len() > 1 {
            // Tiebreaker: player 2 (seat_index=1) wins
            players_with_max
                .iter()
                .filter(|p| p.seat_index == 1)
                .map(|p| p.player_id.clone())
                .collect::<Vec<_>>()
        } else {
            players_with_max
                .iter()
                .map(|p| p.player_id.clone())
                .collect()
        };

        let events = vec![Event {
            event_type: "game_ended".into(),
            player_id: None,
            payload: serde_json::json!({
                "final_scores": &final_scores,
                "winners": &winners,
            }),
        }];

        TypedTransitionResult {
            state,
            events,
            next_phase: Phase {
                name: "game_over".into(),
                auto_resolve: false,
                concurrent_mode: None,
                expected_actions: vec![],
                metadata: serde_json::json!({}),
            },
            scores: final_scores.clone(),
            game_over: Some(GameResult {
                winners,
                final_scores,
                reason: "normal".into(),
                details: HashMap::new(),
            }),
        }
    }
}

fn make_place_tile_phase(player_index: usize, player_id: &str) -> Phase {
    Phase {
        name: "place_tile".into(),
        concurrent_mode: Some(ConcurrentMode::Sequential),
        expected_actions: vec![ExpectedAction {
            player_id: player_id.into(),
            action_type: "place_tile".into(),
            constraints: HashMap::new(),
            timeout_ms: None,
        }],
        auto_resolve: false,
        metadata: serde_json::json!({"player_index": player_index}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_players() -> Vec<Player> {
        vec![
            Player {
                player_id: "p1".into(),
                display_name: "Player 1".into(),
                seat_index: 0,
                is_bot: false,
                bot_id: None,
            },
            Player {
                player_id: "p2".into(),
                display_name: "Player 2".into(),
                seat_index: 1,
                is_bot: false,
                bot_id: None,
            },
        ]
    }

    fn default_config() -> GameConfig {
        GameConfig {
            options: serde_json::json!({}),
            random_seed: None,
        }
    }

    #[test]
    fn test_metadata() {
        let plugin = EinsteinDojoPlugin;
        assert_eq!(plugin.game_id(), "einstein_dojo");
        assert_eq!(plugin.display_name(), "Ein Stein Dojo");
        assert_eq!(plugin.min_players(), 2);
        assert_eq!(plugin.max_players(), 2);
    }

    #[test]
    fn test_create_initial_state() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (state, phase, events) = plugin.create_initial_state(&players, &default_config());

        assert!(state.board.kite_owners.is_empty());
        assert!(state.board.placed_pieces.is_empty());
        assert_eq!(state.tiles_remaining["p1"], 16);
        assert_eq!(state.tiles_remaining["p2"], 16);
        assert_eq!(state.scores["p1"], 0);
        assert_eq!(state.scores["p2"], 0);
        assert_eq!(state.current_player_index, 0);

        assert_eq!(phase.name, "place_tile");
        assert!(!phase.auto_resolve);
        assert_eq!(phase.expected_actions[0].player_id, "p1");

        assert_eq!(events.len(), 1);
        assert_eq!(events[0].event_type, "game_started");
    }

    #[test]
    fn test_valid_actions_at_start() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (state, phase, _) = plugin.create_initial_state(&players, &default_config());

        let actions = plugin.get_valid_actions(&state, &phase, "p1");
        // Empty board, anchor (0,0), 12 orientations = at least 12 valid placements
        assert!(actions.len() >= 12);

        // Wrong player gets no actions
        let actions_p2 = plugin.get_valid_actions(&state, &phase, "p2");
        assert!(actions_p2.is_empty());
    }

    #[test]
    fn test_place_first_tile() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (state, phase, _) = plugin.create_initial_state(&players, &default_config());

        let action = Action {
            action_type: "place_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({"anchor_q": 0, "anchor_r": 0, "orientation": 0}),
        };

        assert!(plugin.validate_action(&state, &phase, &action).is_none());

        let result = plugin.apply_action(&state, &phase, &action, &players);
        assert_eq!(result.state.board.kite_owners.len(), 8);
        assert_eq!(result.state.board.placed_pieces.len(), 1);
        assert_eq!(result.state.tiles_remaining["p1"], 15);
        assert_eq!(result.next_phase.name, "score_check");
        assert!(result.next_phase.auto_resolve);
    }

    #[test]
    fn test_score_check_advances_turn() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (state, phase, _) = plugin.create_initial_state(&players, &default_config());

        // Place tile
        let action = Action {
            action_type: "place_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({"anchor_q": 0, "anchor_r": 0, "orientation": 0}),
        };
        let result = plugin.apply_action(&state, &phase, &action, &players);

        // Score check (auto-resolve, action is ignored)
        let score_action = Action {
            action_type: "score_check".into(),
            player_id: "".into(),
            payload: serde_json::json!({}),
        };
        let result2 =
            plugin.apply_action(&result.state, &result.next_phase, &score_action, &players);

        assert_eq!(result2.next_phase.name, "place_tile");
        assert_eq!(result2.next_phase.expected_actions[0].player_id, "p2");
        assert_eq!(result2.state.current_player_index, 1);
    }

    #[test]
    fn test_full_turn_cycle() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (mut state, mut phase, _) = plugin.create_initial_state(&players, &default_config());

        // P1 places tile
        let action1 = Action {
            action_type: "place_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({"anchor_q": 0, "anchor_r": 0, "orientation": 0}),
        };
        let r = plugin.apply_action(&state, &phase, &action1, &players);
        state = r.state;
        phase = r.next_phase;

        // Score check
        let sc = Action {
            action_type: "score_check".into(),
            player_id: "".into(),
            payload: serde_json::json!({}),
        };
        let r = plugin.apply_action(&state, &phase, &sc, &players);
        state = r.state;
        phase = r.next_phase;

        assert_eq!(phase.name, "place_tile");
        assert_eq!(phase.expected_actions[0].player_id, "p2");

        // P2 places tile — pick first valid action
        let valid = plugin.get_valid_actions(&state, &phase, "p2");
        assert!(!valid.is_empty());
        let action2 = Action {
            action_type: "place_tile".into(),
            player_id: "p2".into(),
            payload: valid[0].clone(),
        };
        let r = plugin.apply_action(&state, &phase, &action2, &players);
        assert_eq!(r.state.tiles_remaining["p2"], 15);
        assert_eq!(r.next_phase.name, "score_check");
    }

    #[test]
    fn test_json_roundtrip() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (state, _, _) = plugin.create_initial_state(&players, &default_config());

        let json = plugin.encode_state(&state);
        let decoded = plugin.decode_state(&json);

        assert_eq!(decoded.tiles_remaining["p1"], state.tiles_remaining["p1"]);
        assert_eq!(decoded.current_player_index, state.current_player_index);
    }

    #[test]
    fn test_forfeit_handling() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (state, phase, _) = plugin.create_initial_state(&players, &default_config());

        let result = plugin.on_player_forfeit(&state, &phase, "p1", &players);
        assert!(result.is_some());
        let r = result.unwrap();
        assert_eq!(r.next_phase.expected_actions[0].player_id, "p2");
        assert_eq!(r.state.current_player_index, 1);
    }

    #[test]
    fn test_full_game_loop() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();
        let (mut state, mut phase, _) = plugin.create_initial_state(&players, &default_config());

        let mut turns = 0;
        let max_turns = 100; // safety limit

        while phase.name != "game_over" && turns < max_turns {
            if phase.name == "score_check" {
                let sc = Action {
                    action_type: "score_check".into(),
                    player_id: "".into(),
                    payload: serde_json::json!({}),
                };
                let r = plugin.apply_action(&state, &phase, &sc, &players);
                state = r.state;
                phase = r.next_phase;
                if r.game_over.is_some() {
                    break;
                }
                continue;
            }

            if phase.name == "choose_main_conflict" {
                let current_pid = phase.expected_actions[0].player_id.clone();
                let valid = plugin.get_valid_actions(&state, &phase, &current_pid);
                let action = Action {
                    action_type: "choose_main_conflict".into(),
                    player_id: current_pid,
                    payload: valid[0].clone(),
                };
                let r = plugin.apply_action(&state, &phase, &action, &players);
                state = r.state;
                phase = r.next_phase;
                continue;
            }

            let current_pid = phase.expected_actions[0].player_id.clone();
            let valid = plugin.get_valid_actions(&state, &phase, &current_pid);

            if valid.is_empty() {
                // No valid moves — shouldn't happen in normal play but handle gracefully
                break;
            }

            let action = Action {
                action_type: "place_tile".into(),
                player_id: current_pid,
                payload: valid[0].clone(),
            };

            let r = plugin.apply_action(&state, &phase, &action, &players);
            state = r.state;
            phase = r.next_phase;
            turns += 1;

            if r.game_over.is_some() {
                break;
            }
        }

        // Each player has 16 tiles, game should end after 32 place_tile actions
        assert!(turns <= 32, "game should end within 32 turns, took {turns}");
        assert!(turns > 0, "game should have at least one turn");

        // Verify tiles are exhausted for at least one player
        let p1_left = state.tiles_remaining["p1"];
        let p2_left = state.tiles_remaining["p2"];
        assert!(
            p1_left == 0 || p2_left == 0,
            "at least one player should have 0 tiles, got p1={p1_left} p2={p2_left}"
        );
    }

    #[test]
    fn test_tiebreaker_player2_wins() {
        let plugin = EinsteinDojoPlugin;
        let players = test_players();

        // Create a state where both players have score 0 and p1 has 0 tiles left
        let state = EinsteinDojoState {
            board: Board::new(),
            tiles_remaining: [("p1".into(), 0), ("p2".into(), 5)]
                .into_iter()
                .collect(),
            scores: [("p1".into(), 0), ("p2".into(), 0)]
                .into_iter()
                .collect(),
            current_player_index: 0,
            main_conflict: None,
        };

        let score_phase = Phase {
            name: "score_check".into(),
            auto_resolve: true,
            concurrent_mode: None,
            expected_actions: vec![],
            metadata: serde_json::json!({"player_index": 0}),
        };

        let r = plugin.apply_action(&state, &score_phase, &Action {
            action_type: "score_check".into(),
            player_id: "".into(),
            payload: serde_json::json!({}),
        }, &players);

        assert!(r.game_over.is_some());
        let game_over = r.game_over.unwrap();
        assert_eq!(game_over.winners, vec!["p2"]);
    }
}
