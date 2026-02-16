//! GamePlugin traits — the interface every game must implement.
//! Mirrors backend/src/engine/protocol.py.
//!
//! Games implement `TypedGamePlugin` with strongly-typed state.
//! `GamePlugin` (JSON boundary) is auto-derived via `JsonAdapter`.

use crate::engine::models::*;
use std::collections::HashMap;

/// Transition result with typed game state.
pub struct TypedTransitionResult<S> {
    pub state: S,
    pub events: Vec<Event>,
    pub next_phase: Phase,
    pub scores: HashMap<String, f64>,
    pub game_over: Option<GameResult>,
}

/// The primary trait every game implements. Uses strongly-typed state.
pub trait TypedGamePlugin: Send + Sync {
    type State: Clone + Send + Sync;

    // --- Metadata ---
    fn game_id(&self) -> &str;
    fn display_name(&self) -> &str;
    fn min_players(&self) -> u32;
    fn max_players(&self) -> u32;
    fn description(&self) -> &str;
    fn disconnect_policy(&self) -> &str;

    // --- Serialization ---
    fn decode_state(&self, game_data: &serde_json::Value) -> Self::State;
    fn encode_state(&self, state: &Self::State) -> serde_json::Value;

    // --- Core game logic ---
    fn create_initial_state(
        &self,
        players: &[Player],
        config: &GameConfig,
    ) -> (Self::State, Phase, Vec<Event>);

    fn get_valid_actions(
        &self,
        state: &Self::State,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value>;

    fn validate_action(
        &self,
        state: &Self::State,
        phase: &Phase,
        action: &Action,
    ) -> Option<String>;

    fn apply_action(
        &self,
        state: &Self::State,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TypedTransitionResult<Self::State>;

    fn get_player_view(
        &self,
        state: &Self::State,
        phase: &Phase,
        player_id: Option<&str>,
        players: &[Player],
    ) -> serde_json::Value;

    fn get_scores(&self, state: &Self::State) -> HashMap<String, f64>;

    // --- Methods with defaults ---

    fn get_spectator_summary(
        &self,
        state: &Self::State,
        phase: &Phase,
        players: &[Player],
    ) -> serde_json::Value {
        self.get_player_view(state, phase, None, players)
    }

    fn state_to_ai_view(
        &self,
        state: &Self::State,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> serde_json::Value {
        self.get_player_view(state, phase, Some(player_id), players)
    }

    fn parse_ai_action(
        &self,
        response: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Action;

    fn on_player_forfeit(
        &self,
        _state: &Self::State,
        _phase: &Phase,
        _player_id: &str,
        _players: &[Player],
    ) -> Option<TypedTransitionResult<Self::State>> {
        None
    }

    // --- MCTS-specific ---

    /// Randomize hidden information for MCTS determinization.
    fn determinize(&self, _state: &mut Self::State) {}

    /// Return context for AMAF key generation (e.g., current tile type).
    fn amaf_context(&self, _state: &Self::State) -> String {
        String::new()
    }
}

// =========================================================================
// GamePlugin — JSON boundary trait for gRPC server
// =========================================================================

/// JSON-based game plugin trait used at the gRPC boundary.
/// Not implemented directly by games — use `JsonAdapter` to derive it.
pub trait GamePlugin: Send + Sync {
    fn game_id(&self) -> &str;
    fn display_name(&self) -> &str;
    fn min_players(&self) -> u32;
    fn max_players(&self) -> u32;
    fn description(&self) -> &str;
    fn disconnect_policy(&self) -> &str;

    fn create_initial_state(
        &self,
        players: &[Player],
        config: &GameConfig,
    ) -> (serde_json::Value, Phase, Vec<Event>);

    fn get_valid_actions(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value>;

    fn validate_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
    ) -> Option<String>;

    fn apply_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TransitionResult;

    fn get_player_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: Option<&str>,
        players: &[Player],
    ) -> serde_json::Value;

    fn get_spectator_summary(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        players: &[Player],
    ) -> serde_json::Value;

    fn state_to_ai_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> serde_json::Value;

    fn parse_ai_action(
        &self,
        response: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Action;

    fn on_player_forfeit(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> Option<TransitionResult>;
}

// =========================================================================
// JsonAdapter — auto-derives GamePlugin from TypedGamePlugin
// =========================================================================

/// Wraps a `TypedGamePlugin` to provide a `GamePlugin` (JSON boundary) impl.
/// Used by the gRPC server and GameRegistry.
pub struct JsonAdapter<P: TypedGamePlugin>(pub P);

impl<P: TypedGamePlugin> GamePlugin for JsonAdapter<P> {
    fn game_id(&self) -> &str { self.0.game_id() }
    fn display_name(&self) -> &str { self.0.display_name() }
    fn min_players(&self) -> u32 { self.0.min_players() }
    fn max_players(&self) -> u32 { self.0.max_players() }
    fn description(&self) -> &str { self.0.description() }
    fn disconnect_policy(&self) -> &str { self.0.disconnect_policy() }

    fn create_initial_state(
        &self,
        players: &[Player],
        config: &GameConfig,
    ) -> (serde_json::Value, Phase, Vec<Event>) {
        let (state, phase, events) = self.0.create_initial_state(players, config);
        (self.0.encode_state(&state), phase, events)
    }

    fn get_valid_actions(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value> {
        let state = self.0.decode_state(game_data);
        self.0.get_valid_actions(&state, phase, player_id)
    }

    fn validate_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
    ) -> Option<String> {
        let state = self.0.decode_state(game_data);
        self.0.validate_action(&state, phase, action)
    }

    fn apply_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TransitionResult {
        let state = self.0.decode_state(game_data);
        let typed = self.0.apply_action(&state, phase, action, players);
        TransitionResult {
            game_data: self.0.encode_state(&typed.state),
            events: typed.events,
            next_phase: typed.next_phase,
            scores: typed.scores,
            game_over: typed.game_over,
        }
    }

    fn get_player_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: Option<&str>,
        players: &[Player],
    ) -> serde_json::Value {
        let state = self.0.decode_state(game_data);
        self.0.get_player_view(&state, phase, player_id, players)
    }

    fn get_spectator_summary(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        players: &[Player],
    ) -> serde_json::Value {
        let state = self.0.decode_state(game_data);
        self.0.get_spectator_summary(&state, phase, players)
    }

    fn state_to_ai_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> serde_json::Value {
        let state = self.0.decode_state(game_data);
        self.0.state_to_ai_view(&state, phase, player_id, players)
    }

    fn parse_ai_action(
        &self,
        response: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Action {
        self.0.parse_ai_action(response, phase, player_id)
    }

    fn on_player_forfeit(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> Option<TransitionResult> {
        let state = self.0.decode_state(game_data);
        self.0.on_player_forfeit(&state, phase, player_id, players)
            .map(|typed| TransitionResult {
                game_data: self.0.encode_state(&typed.state),
                events: typed.events,
                next_phase: typed.next_phase,
                scores: typed.scores,
                game_over: typed.game_over,
            })
    }
}
