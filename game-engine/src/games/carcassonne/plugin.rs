//! CarcassonnePlugin — implements GamePlugin and TypedGamePlugin traits.
//! Mirrors backend/src/games/carcassonne/plugin.py.

use std::collections::HashMap;

use crate::engine::models::*;
use crate::engine::plugin::{GamePlugin, TypedGamePlugin, TypedTransitionResult};
use super::board::{can_place_tile, recalculate_open_positions, tile_has_valid_placement};
use super::features::{
    check_monastery_completion, create_and_merge_features,
    initialize_features_from_tile, is_feature_complete,
};
use super::meeples::{can_place_meeple, return_meeples};
use super::scoring::{score_completed_feature, score_end_game};
use super::tiles::{STARTING_TILE_ID, build_tile_bag, get_rotated_features};
use super::types::*;

pub struct CarcassonnePlugin;

// ================================================================== //
//  TypedGamePlugin implementation (fast path for MCTS / Arena)
// ================================================================== //

impl TypedGamePlugin for CarcassonnePlugin {
    type State = CarcassonneState;

    fn decode_state(&self, game_data: &serde_json::Value) -> CarcassonneState {
        serde_json::from_value(game_data.clone()).expect("Failed to decode CarcassonneState")
    }

    fn encode_state(&self, state: &CarcassonneState) -> serde_json::Value {
        state.to_json()
    }

    fn get_valid_actions_typed(
        &self,
        state: &CarcassonneState,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value> {
        match phase.name.as_str() {
            "place_tile" => get_valid_tile_placements_typed(state, player_id),
            "place_meeple" => get_valid_meeple_placements_typed(state, player_id),
            _ => vec![],
        }
    }

    fn apply_action_typed(
        &self,
        state: &CarcassonneState,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TypedTransitionResult<CarcassonneState> {
        let mut s = state.clone();
        match phase.name.as_str() {
            "draw_tile" => apply_draw_tile_typed(&mut s, phase, players),
            "place_tile" => apply_place_tile_typed(&mut s, phase, action, players),
            "place_meeple" => apply_place_meeple_typed(&mut s, phase, action, players),
            "score_check" => apply_score_check_typed(&mut s, phase, players),
            "end_game_scoring" => apply_end_game_scoring_typed(&mut s, phase, players),
            _ => TypedTransitionResult {
                state: s,
                events: vec![],
                next_phase: phase.clone(),
                scores: HashMap::new(),
                game_over: None,
            },
        }
    }

    fn get_scores_typed(&self, state: &CarcassonneState) -> HashMap<String, f64> {
        state.float_scores()
    }

    fn determinize(&self, state: &mut CarcassonneState) {
        use rand::seq::SliceRandom;
        let mut rng = rand::thread_rng();
        state.tile_bag.shuffle(&mut rng);
    }

    fn amaf_context(&self, state: &CarcassonneState) -> String {
        state.current_tile.clone().unwrap_or_default()
    }
}

// ================================================================== //
//  GamePlugin implementation (JSON boundary for gRPC)
// ================================================================== //

impl GamePlugin for CarcassonnePlugin {
    fn game_id(&self) -> &str { "carcassonne" }
    fn display_name(&self) -> &str { "Carcassonne" }
    fn min_players(&self) -> u32 { 2 }
    fn max_players(&self) -> u32 { 5 }
    fn description(&self) -> &str {
        "Build a medieval landscape by placing tiles and claiming features with meeples."
    }
    fn disconnect_policy(&self) -> &str { "forfeit_player" }

    fn create_initial_state(
        &self,
        players: &[Player],
        config: &GameConfig,
    ) -> (serde_json::Value, Phase, Vec<Event>) {
        let mut tile_bag = build_tile_bag(None);

        use rand::seq::SliceRandom;
        use rand::SeedableRng;
        let seed = config.random_seed.unwrap_or(0);
        let mut rng = rand::rngs::StdRng::seed_from_u64(seed);
        tile_bag.shuffle(&mut rng);

        if let Some(tile_count) = config.options.get("tile_count").and_then(|v| v.as_u64()) {
            let tc = tile_count as usize;
            if tc < tile_bag.len() {
                tile_bag.truncate(tc);
            }
        }

        let mut board_tiles: HashMap<String, PlacedTile> = HashMap::new();
        board_tiles.insert("0,0".into(), PlacedTile {
            tile_type_id: STARTING_TILE_ID.into(),
            rotation: 0,
        });
        let open_positions = recalculate_open_positions(&board_tiles);

        let (features, tile_feature_map) =
            initialize_features_from_tile(STARTING_TILE_ID, "0,0", 0);

        let meeple_supply: HashMap<String, i32> = players
            .iter()
            .map(|p| (p.player_id.clone(), 7))
            .collect();
        let scores: HashMap<String, i64> = players
            .iter()
            .map(|p| (p.player_id.clone(), 0))
            .collect();

        let state = CarcassonneState {
            board: Board { tiles: board_tiles, open_positions },
            tile_bag,
            current_tile: None,
            last_placed_position: None,
            features,
            tile_feature_map,
            meeple_supply,
            scores,
            current_player_index: 0,
            rng_state: None,
            forfeited_players: vec![],
            end_game_breakdown: None,
        };

        let first_phase = Phase {
            name: "draw_tile".into(),
            auto_resolve: true,
            concurrent_mode: None,
            expected_actions: vec![],
            metadata: serde_json::json!({"player_index": 0}),
        };

        let events = vec![
            Event {
                event_type: "game_started".into(),
                player_id: None,
                payload: serde_json::json!({
                    "players": players.iter().map(|p| &p.player_id).collect::<Vec<_>>(),
                }),
            },
            Event {
                event_type: "starting_tile_placed".into(),
                player_id: None,
                payload: serde_json::json!({
                    "tile": STARTING_TILE_ID,
                    "position": "0,0",
                }),
            },
        ];

        (state.to_json(), first_phase, events)
    }

    fn get_valid_actions(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value> {
        let state = self.decode_state(game_data);
        self.get_valid_actions_typed(&state, phase, player_id)
    }

    fn validate_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
    ) -> Option<String> {
        let state = self.decode_state(game_data);
        match phase.name.as_str() {
            "place_tile" => validate_place_tile_typed(&state, action),
            "place_meeple" => validate_place_meeple_typed(&state, action),
            _ => None,
        }
    }

    fn apply_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
        players: &[Player],
    ) -> TransitionResult {
        let state = self.decode_state(game_data);
        let typed = self.apply_action_typed(&state, phase, action, players);
        TransitionResult {
            game_data: self.encode_state(&typed.state),
            events: typed.events,
            next_phase: typed.next_phase,
            scores: typed.scores,
            game_over: typed.game_over,
        }
    }

    fn get_player_view(
        &self,
        game_data: &serde_json::Value,
        _phase: &Phase,
        _player_id: Option<&str>,
        _players: &[Player],
    ) -> serde_json::Value {
        let state: CarcassonneState = self.decode_state(game_data);
        let mut view = serde_json::json!({
            "board": state.board,
            "features": state.features,
            "tile_feature_map": state.tile_feature_map,
            "current_tile": state.current_tile,
            "tiles_remaining": state.tile_bag.len(),
            "meeple_supply": state.meeple_supply,
            "scores": state.scores,
            "last_placed_position": state.last_placed_position,
        });
        if let Some(ref breakdown) = state.end_game_breakdown {
            view["end_game_breakdown"] = breakdown.clone();
        }
        view
    }

    fn get_spectator_summary(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        players: &[Player],
    ) -> serde_json::Value {
        self.get_player_view(game_data, phase, None, players)
    }

    fn state_to_ai_view(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> serde_json::Value {
        let state = self.decode_state(game_data);
        let mut view = self.get_player_view(game_data, phase, Some(player_id), players);
        let valid = self.get_valid_actions_typed(&state, phase, player_id);
        view["valid_actions"] = serde_json::json!(valid);
        view["my_meeples"] = serde_json::json!(
            state.meeple_supply.get(player_id).copied().unwrap_or(0)
        );
        view
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
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        players: &[Player],
    ) -> Option<TransitionResult> {
        if !matches!(phase.name.as_str(), "place_tile" | "place_meeple" | "score_check") {
            return None;
        }

        let player_index = phase.metadata.get("player_index")?.as_u64()? as usize;
        let mut state = self.decode_state(game_data);

        // Put current tile back if one was drawn
        if let Some(tile) = state.current_tile.take() {
            state.tile_bag.insert(0, tile);
        }
        state.last_placed_position = None;

        let next_index = find_next_player_typed(&state, players, player_index);

        let events = vec![Event {
            event_type: "turn_skipped".into(),
            player_id: Some(player_id.into()),
            payload: serde_json::json!({"reason": "forfeit"}),
        }];

        let next_phase = Phase {
            name: "draw_tile".into(),
            auto_resolve: true,
            concurrent_mode: None,
            expected_actions: vec![],
            metadata: serde_json::json!({"player_index": next_index}),
        };

        Some(TransitionResult {
            game_data: state.to_json(),
            events,
            next_phase,
            scores: state.float_scores(),
            game_over: None,
        })
    }
}

// ================================================================== //
//  Typed phase handlers
// ================================================================== //

fn apply_draw_tile_typed(
    state: &mut CarcassonneState,
    phase: &Phase,
    players: &[Player],
) -> TypedTransitionResult<CarcassonneState> {
    if state.tile_bag.is_empty() {
        return TypedTransitionResult {
            state: state.clone(),
            events: vec![Event {
                event_type: "tile_bag_empty".into(),
                player_id: None,
                payload: serde_json::json!({}),
            }],
            next_phase: Phase {
                name: "end_game_scoring".into(),
                auto_resolve: true,
                concurrent_mode: None,
                expected_actions: vec![],
                metadata: serde_json::json!({}),
            },
            scores: state.float_scores(),
            game_over: None,
        };
    }

    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let player = &players[player_index];

    let mut drawn_tile = state.tile_bag.remove(0);

    // Skip unplaceable tiles
    while !tile_has_valid_placement(&state.board.tiles, &state.board.open_positions, &drawn_tile) {
        if state.tile_bag.is_empty() {
            return TypedTransitionResult {
                state: state.clone(),
                events: vec![
                    Event {
                        event_type: "tile_discarded".into(),
                        player_id: Some(player.player_id.clone()),
                        payload: serde_json::json!({
                            "tile": drawn_tile,
                            "reason": "no_valid_placement",
                        }),
                    },
                    Event {
                        event_type: "tile_bag_empty".into(),
                        player_id: None,
                        payload: serde_json::json!({}),
                    },
                ],
                next_phase: Phase {
                    name: "end_game_scoring".into(),
                    auto_resolve: true,
                    concurrent_mode: None,
                    expected_actions: vec![],
                    metadata: serde_json::json!({}),
                },
                scores: state.float_scores(),
                game_over: None,
            };
        }
        drawn_tile = state.tile_bag.remove(0);
    }

    state.current_tile = Some(drawn_tile.clone());

    let events = vec![Event {
        event_type: "tile_drawn".into(),
        player_id: Some(player.player_id.clone()),
        payload: serde_json::json!({
            "tile": drawn_tile,
            "tiles_remaining": state.tile_bag.len(),
        }),
    }];

    let next_phase = Phase {
        name: "place_tile".into(),
        auto_resolve: false,
        concurrent_mode: Some(ConcurrentMode::Sequential),
        expected_actions: vec![ExpectedAction {
            player_id: player.player_id.clone(),
            action_type: "place_tile".into(),
            constraints: Default::default(),
            timeout_ms: None,
        }],
        metadata: serde_json::json!({"player_index": player_index}),
    };

    TypedTransitionResult {
        state: state.clone(),
        events,
        next_phase,
        scores: state.float_scores(),
        game_over: None,
    }
}

fn apply_place_tile_typed(
    state: &mut CarcassonneState,
    phase: &Phase,
    action: &Action,
    players: &[Player],
) -> TypedTransitionResult<CarcassonneState> {
    let x = action.payload["x"].as_i64().unwrap_or(0);
    let y = action.payload["y"].as_i64().unwrap_or(0);
    let rotation = action.payload["rotation"].as_u64().unwrap_or(0) as u32;
    let pos_key = format!("{},{}", x, y);
    let tile_type_id = state.current_tile.clone().unwrap_or_default();
    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let player = &players[player_index];

    // Place tile on board
    state.board.tiles.insert(pos_key.clone(), PlacedTile {
        tile_type_id: tile_type_id.clone(),
        rotation,
    });

    // Recalculate open positions
    state.board.open_positions = recalculate_open_positions(&state.board.tiles);

    state.last_placed_position = Some(pos_key.clone());
    state.current_tile = None;

    // Create features and merge with adjacent
    let merge_events = create_and_merge_features(state, &tile_type_id, &pos_key, rotation);

    let mut events = vec![Event {
        event_type: "tile_placed".into(),
        player_id: Some(player.player_id.clone()),
        payload: serde_json::json!({
            "tile": tile_type_id,
            "x": x,
            "y": y,
            "rotation": rotation,
        }),
    }];
    events.extend(merge_events);

    let next_phase = Phase {
        name: "place_meeple".into(),
        auto_resolve: false,
        concurrent_mode: Some(ConcurrentMode::Sequential),
        expected_actions: vec![ExpectedAction {
            player_id: player.player_id.clone(),
            action_type: "place_meeple".into(),
            constraints: Default::default(),
            timeout_ms: None,
        }],
        metadata: serde_json::json!({"player_index": player_index}),
    };

    TypedTransitionResult {
        state: state.clone(),
        events,
        next_phase,
        scores: state.float_scores(),
        game_over: None,
    }
}

fn apply_place_meeple_typed(
    state: &mut CarcassonneState,
    phase: &Phase,
    action: &Action,
    players: &[Player],
) -> TypedTransitionResult<CarcassonneState> {
    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let player = &players[player_index];
    let mut events: Vec<Event> = Vec::new();

    let skip = action.payload.get("skip").and_then(|v| v.as_bool()).unwrap_or(false);

    if !skip {
        let spot = action.payload["meeple_spot"].as_str().unwrap_or("").to_string();
        let pos = state.last_placed_position.clone().unwrap_or_default();

        let feature_id = state.tile_feature_map
            .get(&pos)
            .and_then(|spots| spots.get(&spot))
            .cloned()
            .unwrap_or_default();

        // Decrement meeple supply
        if let Some(supply) = state.meeple_supply.get_mut(&player.player_id) {
            *supply -= 1;
        }

        // Add meeple to feature
        if let Some(feature) = state.features.get_mut(&feature_id) {
            feature.meeples.push(PlacedMeeple {
                player_id: player.player_id.clone(),
                position: pos.clone(),
                spot: spot.clone(),
            });
        }

        events.push(Event {
            event_type: "meeple_placed".into(),
            player_id: Some(player.player_id.clone()),
            payload: serde_json::json!({
                "position": pos,
                "spot": spot,
                "feature_id": feature_id,
            }),
        });
    } else {
        events.push(Event {
            event_type: "meeple_skipped".into(),
            player_id: Some(player.player_id.clone()),
            payload: serde_json::json!({}),
        });
    }

    let next_phase = Phase {
        name: "score_check".into(),
        auto_resolve: true,
        concurrent_mode: None,
        expected_actions: vec![],
        metadata: serde_json::json!({"player_index": player_index}),
    };

    TypedTransitionResult {
        state: state.clone(),
        events,
        next_phase,
        scores: state.float_scores(),
        game_over: None,
    }
}

fn apply_score_check_typed(
    state: &mut CarcassonneState,
    phase: &Phase,
    players: &[Player],
) -> TypedTransitionResult<CarcassonneState> {
    let mut events: Vec<Event> = Vec::new();

    let last_pos = state.last_placed_position.clone().unwrap_or_default();
    let mut checked_features: std::collections::HashSet<String> =
        std::collections::HashSet::new();

    // Collect feature IDs from the placed tile
    let spots: Vec<(String, String)> = state.tile_feature_map
        .get(&last_pos)
        .map(|m| m.iter().map(|(s, f)| (s.clone(), f.clone())).collect())
        .unwrap_or_default();

    for (_spot, feature_id) in spots {
        if checked_features.contains(&feature_id) {
            continue;
        }
        checked_features.insert(feature_id.clone());

        let is_already_complete = state.features.get(&feature_id)
            .map(|f| f.is_complete).unwrap_or(true);
        if is_already_complete {
            continue;
        }

        let complete = {
            let Some(feature) = state.features.get(&feature_id) else { continue };
            is_feature_complete(state, feature)
        };

        if !complete {
            continue;
        }

        // Mark complete
        if let Some(feat) = state.features.get_mut(&feature_id) {
            feat.is_complete = true;
        }

        let point_awards = score_completed_feature(&state.features[&feature_id]);

        let ft = state.features[&feature_id].feature_type;
        let tiles = state.features[&feature_id].tiles.clone();

        for (pid, points) in &point_awards {
            *state.scores.entry(pid.clone()).or_insert(0) += points;
            events.push(Event {
                event_type: "feature_scored".into(),
                player_id: Some(pid.clone()),
                payload: serde_json::json!({
                    "feature_id": feature_id,
                    "feature_type": ft,
                    "points": points,
                    "tiles": tiles,
                }),
            });
        }

        let meeple_events = return_meeples(state, &feature_id);
        events.extend(meeple_events);
    }

    // Check monasteries near the placed tile
    let (monastery_events, monastery_scores) = check_monastery_completion(state, &last_pos);
    events.extend(monastery_events);
    for (pid, points) in &monastery_scores {
        *state.scores.entry(pid.clone()).or_insert(0) += points;
    }

    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let next_index = find_next_player_typed(state, players, player_index);

    let next_phase = Phase {
        name: "draw_tile".into(),
        auto_resolve: true,
        concurrent_mode: None,
        expected_actions: vec![],
        metadata: serde_json::json!({"player_index": next_index}),
    };

    TypedTransitionResult {
        state: state.clone(),
        events,
        next_phase,
        scores: state.float_scores(),
        game_over: None,
    }
}

fn apply_end_game_scoring_typed(
    state: &mut CarcassonneState,
    _phase: &Phase,
    _players: &[Player],
) -> TypedTransitionResult<CarcassonneState> {
    let mut events: Vec<Event> = Vec::new();

    let (end_scores, breakdown) = score_end_game(state);
    state.end_game_breakdown = Some(serde_json::json!(breakdown));

    for (pid, points) in &end_scores {
        *state.scores.entry(pid.clone()).or_insert(0) += points;
        events.push(Event {
            event_type: "end_game_points".into(),
            player_id: Some(pid.clone()),
            payload: serde_json::json!({
                "points": points,
                "breakdown": breakdown.get(pid).cloned().unwrap_or_default(),
            }),
        });
    }

    let max_score = state.scores.values().copied().max().unwrap_or(0);
    let winners: Vec<String> = state.scores
        .iter()
        .filter(|(_, &s)| s == max_score)
        .map(|(pid, _)| pid.clone())
        .collect();

    let final_scores = state.float_scores();

    TypedTransitionResult {
        state: state.clone(),
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
            details: Default::default(),
        }),
    }
}

// ================================================================== //
//  Typed valid actions helpers
// ================================================================== //

fn get_valid_tile_placements_typed(
    state: &CarcassonneState,
    player_id: &str,
) -> Vec<serde_json::Value> {
    let current_tile = match &state.current_tile {
        Some(t) => t.as_str(),
        None => return vec![],
    };

    let has_meeples = state.meeple_supply.get(player_id).copied().unwrap_or(0) > 0;

    let mut placements = Vec::new();

    for pos_key in &state.board.open_positions {
        let pos = Position::from_key(pos_key);

        for rotation in [0u32, 90, 180, 270] {
            if can_place_tile(&state.board.tiles, current_tile, pos_key, rotation) {
                let mut meeple_spots: Vec<String> = Vec::new();
                if has_meeples {
                    let rotated_features = get_rotated_features(current_tile, rotation);
                    let mut seen = std::collections::HashSet::new();
                    for feat in &rotated_features {
                        for spot in &feat.meeple_spots {
                            if seen.insert(spot.clone()) {
                                meeple_spots.push(spot.clone());
                            }
                        }
                    }
                }

                placements.push(serde_json::json!({
                    "x": pos.x,
                    "y": pos.y,
                    "rotation": rotation,
                    "meeple_spots": meeple_spots,
                }));
            }
        }
    }

    placements
}

fn get_valid_meeple_placements_typed(
    state: &CarcassonneState,
    player_id: &str,
) -> Vec<serde_json::Value> {
    let last_pos = match &state.last_placed_position {
        Some(p) => p.as_str(),
        None => return vec![serde_json::json!({"skip": true})],
    };

    let placed_tile = match state.board.tiles.get(last_pos) {
        Some(t) => t,
        None => return vec![serde_json::json!({"skip": true})],
    };

    let rotated_features = get_rotated_features(&placed_tile.tile_type_id, placed_tile.rotation);
    let mut spots: Vec<serde_json::Value> = Vec::new();
    let mut seen_spots = std::collections::HashSet::new();

    for tile_feat in &rotated_features {
        for spot in &tile_feat.meeple_spots {
            if !seen_spots.insert(spot.clone()) {
                continue;
            }
            if can_place_meeple(state, player_id, last_pos, spot) {
                spots.push(serde_json::json!({"meeple_spot": spot}));
            }
        }
    }

    spots.push(serde_json::json!({"skip": true}));
    spots
}

// ================================================================== //
//  Typed validation helpers
// ================================================================== //

fn validate_place_tile_typed(
    state: &CarcassonneState,
    action: &Action,
) -> Option<String> {
    let x = action.payload.get("x").and_then(|v| v.as_i64());
    let y = action.payload.get("y").and_then(|v| v.as_i64());
    let rotation = action.payload.get("rotation").and_then(|v| v.as_u64());

    if x.is_none() || y.is_none() || rotation.is_none() {
        return Some("Missing x, y, or rotation in payload".into());
    }
    let rotation = rotation.unwrap() as u32;
    if !matches!(rotation, 0 | 90 | 180 | 270) {
        return Some(format!("Invalid rotation: {}", rotation));
    }

    let pos_key = format!("{},{}", x.unwrap(), y.unwrap());
    let current_tile = match &state.current_tile {
        Some(t) => t.as_str(),
        None => return Some("No tile drawn".into()),
    };

    if !can_place_tile(&state.board.tiles, current_tile, &pos_key, rotation) {
        return Some(format!(
            "Cannot place tile {} at {} with rotation {}",
            current_tile, pos_key, rotation
        ));
    }

    None
}

fn validate_place_meeple_typed(
    state: &CarcassonneState,
    action: &Action,
) -> Option<String> {
    if action.payload.get("skip").and_then(|v| v.as_bool()).unwrap_or(false) {
        return None;
    }

    let spot = match action.payload.get("meeple_spot").and_then(|v| v.as_str()) {
        Some(s) => s,
        None => return Some("Missing meeple_spot in payload".into()),
    };

    let last_pos = match &state.last_placed_position {
        Some(p) => p.as_str(),
        None => return Some("No tile was placed this turn".into()),
    };

    if !can_place_meeple(state, &action.player_id, last_pos, spot) {
        return Some(format!(
            "Cannot place meeple on spot {} at {}",
            spot, last_pos
        ));
    }

    None
}

// ================================================================== //
//  Utility helpers
// ================================================================== //

fn find_next_player_typed(
    state: &CarcassonneState,
    players: &[Player],
    current_index: usize,
) -> usize {
    let forfeited: std::collections::HashSet<&str> = state.forfeited_players
        .iter()
        .map(|s| s.as_str())
        .collect();

    let num_players = players.len();
    let mut next = (current_index + 1) % num_players;
    for _ in 0..num_players {
        if !forfeited.contains(players[next].player_id.as_str()) {
            break;
        }
        next = (next + 1) % num_players;
    }
    next
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_players(n: u32) -> Vec<Player> {
        (0..n)
            .map(|i| Player {
                player_id: format!("p{}", i + 1),
                display_name: format!("Player {}", i + 1),
                seat_index: i as i32,
                is_bot: false,
                bot_id: None,
            })
            .collect()
    }

    #[test]
    fn test_create_initial_state() {
        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({}),
        };

        let (game_data, phase, events) = plugin.create_initial_state(&players, &config);

        assert!(game_data["board"]["tiles"]["0,0"].is_object());
        assert_eq!(
            game_data["board"]["tiles"]["0,0"]["tile_type_id"].as_str().unwrap(),
            "D"
        );

        assert!(game_data["tile_bag"].as_array().unwrap().len() > 0);
        assert_eq!(game_data["meeple_supply"]["p1"].as_i64().unwrap(), 7);
        assert_eq!(game_data["meeple_supply"]["p2"].as_i64().unwrap(), 7);
        assert_eq!(game_data["scores"]["p1"].as_i64().unwrap(), 0);

        assert_eq!(phase.name, "draw_tile");
        assert!(phase.auto_resolve);

        assert_eq!(events.len(), 2);
        assert_eq!(events[0].event_type, "game_started");
        assert_eq!(events[1].event_type, "starting_tile_placed");
    }

    #[test]
    fn test_draw_and_place_tile() {
        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({}),
        };

        let (game_data, phase, _events) = plugin.create_initial_state(&players, &config);

        let draw_action = Action {
            action_type: "draw_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({}),
        };
        let result = plugin.apply_action(&game_data, &phase, &draw_action, &players);

        assert_eq!(result.next_phase.name, "place_tile");
        assert!(result.game_data["current_tile"].as_str().is_some());

        let valid = plugin.get_valid_actions(&result.game_data, &result.next_phase, "p1");
        assert!(!valid.is_empty(), "Should have valid placements");

        let placement = &valid[0];
        let place_action = Action {
            action_type: "place_tile".into(),
            player_id: "p1".into(),
            payload: placement.clone(),
        };

        let place_result = plugin.apply_action(
            &result.game_data,
            &result.next_phase,
            &place_action,
            &players,
        );
        assert_eq!(place_result.next_phase.name, "place_meeple");

        let skip_action = Action {
            action_type: "place_meeple".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({"skip": true}),
        };
        let meeple_result = plugin.apply_action(
            &place_result.game_data,
            &place_result.next_phase,
            &skip_action,
            &players,
        );
        assert_eq!(meeple_result.next_phase.name, "score_check");

        let score_action = Action {
            action_type: "score_check".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({}),
        };
        let score_result = plugin.apply_action(
            &meeple_result.game_data,
            &meeple_result.next_phase,
            &score_action,
            &players,
        );
        assert_eq!(score_result.next_phase.name, "draw_tile");
        assert_eq!(
            score_result.next_phase.metadata["player_index"].as_u64().unwrap(),
            1
        );
    }

    #[test]
    fn test_full_game_loop() {
        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({"tile_count": 5}),
        };

        let (mut game_data, mut phase, _) = plugin.create_initial_state(&players, &config);
        let mut turns = 0;
        let max_turns = 100;

        while phase.name != "game_over" && turns < max_turns {
            turns += 1;

            if phase.auto_resolve {
                let action = Action {
                    action_type: phase.name.clone(),
                    player_id: "system".into(),
                    payload: serde_json::json!({}),
                };
                let result = plugin.apply_action(&game_data, &phase, &action, &players);
                game_data = result.game_data;
                phase = result.next_phase;
                continue;
            }

            let player_id = if !phase.expected_actions.is_empty() {
                phase.expected_actions[0].player_id.clone()
            } else {
                "p1".into()
            };

            let valid = plugin.get_valid_actions(&game_data, &phase, &player_id);
            if valid.is_empty() {
                break;
            }

            let action = Action {
                action_type: phase.name.clone(),
                player_id,
                payload: valid[0].clone(),
            };

            let result = plugin.apply_action(&game_data, &phase, &action, &players);
            game_data = result.game_data;
            phase = result.next_phase;

            if let Some(game_over) = result.game_over {
                assert!(!game_over.winners.is_empty());
                break;
            }
        }

        assert!(
            phase.name == "game_over" || turns < max_turns,
            "Game should complete within {} turns",
            max_turns
        );
    }

    #[test]
    fn test_typed_roundtrip() {
        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({}),
        };

        let (game_data, phase, _) = plugin.create_initial_state(&players, &config);

        // Decode → encode should produce equivalent JSON
        let state = plugin.decode_state(&game_data);
        let re_encoded = plugin.encode_state(&state);

        // Check key fields match
        assert_eq!(
            re_encoded["board"]["tiles"]["0,0"]["tile_type_id"],
            game_data["board"]["tiles"]["0,0"]["tile_type_id"]
        );
        assert_eq!(re_encoded["tile_bag"], game_data["tile_bag"]);
        assert_eq!(re_encoded["scores"], game_data["scores"]);
        assert_eq!(re_encoded["meeple_supply"], game_data["meeple_supply"]);

        // Typed valid actions should match JSON-path valid actions
        let draw_action = Action {
            action_type: "draw_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({}),
        };
        let result = plugin.apply_action(&game_data, &phase, &draw_action, &players);

        let valid_json = plugin.get_valid_actions(&result.game_data, &result.next_phase, "p1");
        let state2 = plugin.decode_state(&result.game_data);
        let valid_typed = plugin.get_valid_actions_typed(&state2, &result.next_phase, "p1");
        assert_eq!(valid_json.len(), valid_typed.len());
    }
}
