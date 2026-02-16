//! GamePlugin trait — the interface every game must implement.
//! Mirrors backend/src/engine/protocol.py.

use crate::engine::models::*;
use std::collections::HashMap;

pub const DISCONNECT_POLICY_ABANDON_ALL: &str = "abandon_all";
pub const DISCONNECT_POLICY_FORFEIT_PLAYER: &str = "forfeit_player";

/// Trait that every game must implement. Equivalent to Python GamePlugin protocol.
pub trait GamePlugin: Send + Sync {
    fn game_id(&self) -> &str;
    fn display_name(&self) -> &str;
    fn min_players(&self) -> u32;
    fn max_players(&self) -> u32;
    fn description(&self) -> &str;
    fn disconnect_policy(&self) -> &str;

    /// Create initial game state from players + config.
    fn create_initial_state(
        &self,
        players: &[Player],
        config: &GameConfig,
    ) -> (serde_json::Value, Phase, Vec<Event>);

    /// Return all legal actions for this player in the current phase.
    fn get_valid_actions(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value>;

    /// Validate an action. Returns None if valid, Some(error) if invalid.
    fn validate_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
    ) -> Option<String>;

    /// Apply a validated action, returning new state + events + next phase.
    fn apply_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TransitionResult;

    /// Filter game_data to what this player can see.
    fn get_player_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: Option<&str>,
        players: &[Player],
    ) -> serde_json::Value;

    /// Return a lightweight summary for spectators.
    fn get_spectator_summary(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        players: &[Player],
    ) -> serde_json::Value;

    /// Serialize game state for a bot.
    fn state_to_ai_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> serde_json::Value;

    /// Parse bot response into Action.
    fn parse_ai_action(
        &self,
        response: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Action;

    /// Called when a forfeited player's turn comes up.
    /// Return Some(TransitionResult) to skip their turn, or None for generic handling.
    fn on_player_forfeit(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> Option<TransitionResult>;
}

// ---------------------------------------------------------------------------
// Typed game plugin — high-performance path for MCTS / Arena
// ---------------------------------------------------------------------------

/// Transition result with typed game state (avoids serde_json::Value).
pub struct TypedTransitionResult<S> {
    pub state: S,
    pub events: Vec<Event>,
    pub next_phase: Phase,
    pub scores: HashMap<String, f64>,
    pub game_over: Option<GameResult>,
}

/// High-performance typed plugin trait.
///
/// Games that implement this get fast `Clone`-based simulation in MCTS and Arena
/// instead of cloning `serde_json::Value` trees. The base `GamePlugin` trait is
/// still used for gRPC boundary calls where JSON ser/deser overhead is acceptable.
pub trait TypedGamePlugin: GamePlugin {
    type State: Clone + Send + Sync;

    /// Deserialize JSON game_data into strongly-typed game state.
    fn decode_state(&self, game_data: &serde_json::Value) -> Self::State;

    /// Serialize strongly-typed game state back to JSON.
    fn encode_state(&self, state: &Self::State) -> serde_json::Value;

    /// Get valid actions from typed state.
    fn get_valid_actions_typed(
        &self,
        state: &Self::State,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value>;

    /// Apply action on typed state — the hot path for MCTS.
    fn apply_action_typed(
        &self,
        state: &Self::State,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TypedTransitionResult<Self::State>;

    /// Extract scores from typed state (used by default MCTS eval).
    fn get_scores_typed(&self, state: &Self::State) -> HashMap<String, f64>;

    /// Randomize hidden information for MCTS determinization.
    /// Default: no-op (games with no hidden info).
    fn determinize(&self, _state: &mut Self::State) {}

    /// Return context for AMAF key generation (e.g., current tile type).
    /// Default: empty (action-only AMAF keys).
    fn amaf_context(&self, _state: &Self::State) -> String {
        String::new()
    }
}
