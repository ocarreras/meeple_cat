//! CarcassonnePlugin — implements GamePlugin trait.
//! Mirrors backend/src/games/carcassonne/plugin.py.

use std::collections::HashMap;

use crate::engine::models::*;
use crate::engine::plugin::GamePlugin;
use super::board::{can_place_tile, recalculate_open_positions, tile_has_valid_placement};
use super::features::{
    check_monastery_completion, create_and_merge_features,
    initialize_features_from_tile, is_feature_complete,
};
use super::meeples::{can_place_meeple, return_meeples};
use super::scoring::{score_completed_feature, score_end_game};
use super::tiles::{STARTING_TILE_ID, build_tile_bag, get_rotated_features};
use super::types::PlacedTile;

pub struct CarcassonnePlugin;

impl GamePlugin for CarcassonnePlugin {
    fn game_id(&self) -> &str {
        "carcassonne"
    }

    fn display_name(&self) -> &str {
        "Carcassonne"
    }

    fn min_players(&self) -> u32 {
        2
    }

    fn max_players(&self) -> u32 {
        5
    }

    fn description(&self) -> &str {
        "Build a medieval landscape by placing tiles and claiming features with meeples."
    }

    fn disconnect_policy(&self) -> &str {
        "forfeit_player"
    }

    fn create_initial_state(
        &self,
        players: &[Player],
        config: &GameConfig,
    ) -> (serde_json::Value, Phase, Vec<Event>) {
        let mut tile_bag = build_tile_bag(None);

        // Shuffle with seed
        use rand::seq::SliceRandom;
        use rand::SeedableRng;
        let seed = config.random_seed.unwrap_or(0);
        let mut rng = rand::rngs::StdRng::seed_from_u64(seed);
        tile_bag.shuffle(&mut rng);

        // Optional tile_count limit
        if let Some(tile_count) = config.options.get("tile_count").and_then(|v| v.as_u64()) {
            let tc = tile_count as usize;
            if tc < tile_bag.len() {
                tile_bag.truncate(tc);
            }
        }

        // Place starting tile at (0,0)
        let mut board_tiles: HashMap<String, PlacedTile> = HashMap::new();
        board_tiles.insert(
            "0,0".into(),
            PlacedTile {
                tile_type_id: STARTING_TILE_ID.into(),
                rotation: 0,
            },
        );
        let open_positions = recalculate_open_positions(&board_tiles);

        let (features, tile_feature_map) =
            initialize_features_from_tile(STARTING_TILE_ID, "0,0", 0);

        let meeple_supply: HashMap<String, i64> = players
            .iter()
            .map(|p| (p.player_id.clone(), 7))
            .collect();
        let scores: HashMap<String, i64> = players
            .iter()
            .map(|p| (p.player_id.clone(), 0))
            .collect();

        let game_data = serde_json::json!({
            "board": {
                "tiles": {
                    "0,0": {
                        "tile_type_id": STARTING_TILE_ID,
                        "rotation": 0,
                    }
                },
                "open_positions": open_positions,
            },
            "tile_bag": tile_bag,
            "current_tile": null,
            "last_placed_position": null,
            "features": features,
            "tile_feature_map": tile_feature_map,
            "meeple_supply": meeple_supply,
            "scores": scores,
            "current_player_index": 0,
        });

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

        (game_data, first_phase, events)
    }

    fn get_valid_actions(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
    ) -> Vec<serde_json::Value> {
        match phase.name.as_str() {
            "place_tile" => get_valid_tile_placements(game_data, player_id),
            "place_meeple" => get_valid_meeple_placements(game_data, player_id),
            _ => vec![],
        }
    }

    fn validate_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        action: &Action,
    ) -> Option<String> {
        match phase.name.as_str() {
            "place_tile" => validate_place_tile(game_data, action),
            "place_meeple" => validate_place_meeple(game_data, action),
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
        let mut gd = game_data.clone();
        match phase.name.as_str() {
            "draw_tile" => apply_draw_tile(&mut gd, phase, players),
            "place_tile" => apply_place_tile(&mut gd, phase, action, players),
            "place_meeple" => apply_place_meeple(&mut gd, phase, action, players),
            "score_check" => apply_score_check(&mut gd, phase, players),
            "end_game_scoring" => apply_end_game_scoring(&mut gd, phase, players),
            _ => TransitionResult {
                game_data: gd,
                events: vec![],
                next_phase: phase.clone(),
                scores: HashMap::new(),
                game_over: None,
            },
        }
    }

    fn get_player_view(
        &self,
        game_data: &serde_json::Value,
        _phase: &Phase,
        _player_id: Option<&str>,
        _players: &[Player],
    ) -> serde_json::Value {
        let mut view = serde_json::json!({
            "board": game_data["board"],
            "features": game_data["features"],
            "tile_feature_map": game_data["tile_feature_map"],
            "current_tile": game_data["current_tile"],
            "tiles_remaining": game_data["tile_bag"].as_array().map(|a| a.len()).unwrap_or(0),
            "meeple_supply": game_data["meeple_supply"],
            "scores": game_data["scores"],
            "last_placed_position": game_data["last_placed_position"],
        });
        if game_data.get("end_game_breakdown").is_some() {
            view["end_game_breakdown"] = game_data["end_game_breakdown"].clone();
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
        let mut view = self.get_player_view(game_data, phase, Some(player_id), players);
        let valid = self.get_valid_actions(game_data, phase, player_id);
        view["valid_actions"] = serde_json::json!(valid);
        view["my_meeples"] = game_data["meeple_supply"]
            .get(player_id)
            .cloned()
            .unwrap_or(serde_json::json!(0));
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
        let mut gd = game_data.clone();

        // Put current tile back if one was drawn
        if !gd["current_tile"].is_null() {
            let tile = gd["current_tile"].as_str().unwrap_or("").to_string();
            if let Some(bag) = gd["tile_bag"].as_array_mut() {
                bag.insert(0, serde_json::json!(tile));
            }
            gd["current_tile"] = serde_json::json!(null);
        }
        gd["last_placed_position"] = serde_json::json!(null);

        let next_index = find_next_player(&gd, players, player_index);

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
            game_data: gd.clone(),
            events,
            next_phase,
            scores: float_scores(&gd["scores"]),
            game_over: None,
        })
    }
}

// ------------------------------------------------------------------ //
//  Phase handlers
// ------------------------------------------------------------------ //

fn apply_draw_tile(
    game_data: &mut serde_json::Value,
    phase: &Phase,
    players: &[Player],
) -> TransitionResult {
    let tile_bag = game_data["tile_bag"].as_array().cloned().unwrap_or_default();

    if tile_bag.is_empty() {
        return TransitionResult {
            game_data: game_data.clone(),
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
            scores: float_scores(&game_data["scores"]),
            game_over: None,
        };
    }

    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let player = &players[player_index];

    // Draw first tile
    let mut bag: Vec<String> = tile_bag
        .iter()
        .filter_map(|v| v.as_str().map(String::from))
        .collect();

    let mut drawn_tile = bag.remove(0);

    // Skip unplaceable tiles
    let board_tiles_val = &game_data["board"]["tiles"];
    let open_positions: Vec<String> = game_data["board"]["open_positions"]
        .as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
        .unwrap_or_default();

    // Build typed board_tiles for placement checks
    let board_tiles = parse_board_tiles(board_tiles_val);

    while !tile_has_valid_placement(&board_tiles, &open_positions, &drawn_tile) {
        if bag.is_empty() {
            game_data["tile_bag"] = serde_json::json!([]);
            return TransitionResult {
                game_data: game_data.clone(),
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
                scores: float_scores(&game_data["scores"]),
                game_over: None,
            };
        }
        drawn_tile = bag.remove(0);
    }

    game_data["current_tile"] = serde_json::json!(drawn_tile);
    game_data["tile_bag"] = serde_json::json!(bag);

    let events = vec![Event {
        event_type: "tile_drawn".into(),
        player_id: Some(player.player_id.clone()),
        payload: serde_json::json!({
            "tile": drawn_tile,
            "tiles_remaining": game_data["tile_bag"].as_array().map(|a| a.len()).unwrap_or(0),
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

    TransitionResult {
        game_data: game_data.clone(),
        events,
        next_phase,
        scores: float_scores(&game_data["scores"]),
        game_over: None,
    }
}

fn apply_place_tile(
    game_data: &mut serde_json::Value,
    phase: &Phase,
    action: &Action,
    players: &[Player],
) -> TransitionResult {
    let x = action.payload["x"].as_i64().unwrap_or(0);
    let y = action.payload["y"].as_i64().unwrap_or(0);
    let rotation = action.payload["rotation"].as_u64().unwrap_or(0) as u32;
    let pos_key = format!("{},{}", x, y);
    let tile_type_id = game_data["current_tile"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let player = &players[player_index];

    // Place tile on board
    game_data["board"]["tiles"][&pos_key] = serde_json::json!({
        "tile_type_id": tile_type_id,
        "rotation": rotation,
    });

    // Recalculate open positions
    let board_tiles = parse_board_tiles(&game_data["board"]["tiles"]);
    let open_positions = recalculate_open_positions(&board_tiles);
    game_data["board"]["open_positions"] = serde_json::json!(open_positions);

    game_data["last_placed_position"] = serde_json::json!(pos_key);
    game_data["current_tile"] = serde_json::json!(null);

    // Create features and merge with adjacent
    let merge_events = create_and_merge_features(game_data, &tile_type_id, &pos_key, rotation);

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

    TransitionResult {
        game_data: game_data.clone(),
        events,
        next_phase,
        scores: float_scores(&game_data["scores"]),
        game_over: None,
    }
}

fn apply_place_meeple(
    game_data: &mut serde_json::Value,
    phase: &Phase,
    action: &Action,
    players: &[Player],
) -> TransitionResult {
    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let player = &players[player_index];
    let mut events: Vec<Event> = Vec::new();

    let skip = action.payload.get("skip").and_then(|v| v.as_bool()).unwrap_or(false);

    if !skip {
        let spot = action.payload["meeple_spot"].as_str().unwrap_or("");
        let pos = game_data["last_placed_position"]
            .as_str()
            .unwrap_or("")
            .to_string();
        let feature_id = game_data["tile_feature_map"][&pos][spot]
            .as_str()
            .unwrap_or("")
            .to_string();

        // Decrement meeple supply
        let current = game_data["meeple_supply"]
            .get(&player.player_id)
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        game_data["meeple_supply"][&player.player_id] = serde_json::json!(current - 1);

        // Add meeple to feature
        let meeple = serde_json::json!({
            "player_id": player.player_id,
            "position": pos,
            "spot": spot,
        });
        if let Some(meeples) = game_data["features"][&feature_id]["meeples"].as_array_mut() {
            meeples.push(meeple);
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

    TransitionResult {
        game_data: game_data.clone(),
        events,
        next_phase,
        scores: float_scores(&game_data["scores"]),
        game_over: None,
    }
}

fn apply_score_check(
    game_data: &mut serde_json::Value,
    phase: &Phase,
    players: &[Player],
) -> TransitionResult {
    let mut events: Vec<Event> = Vec::new();
    let mut scores: HashMap<String, i64> = HashMap::new();

    // Parse current scores
    if let Some(obj) = game_data["scores"].as_object() {
        for (k, v) in obj {
            scores.insert(k.clone(), v.as_i64().unwrap_or(0));
        }
    }

    let last_pos = game_data["last_placed_position"]
        .as_str()
        .unwrap_or("")
        .to_string();
    let mut checked_features: std::collections::HashSet<String> =
        std::collections::HashSet::new();

    // Check features on the placed tile for completion
    let spots: Vec<(String, String)> = game_data["tile_feature_map"]
        .get(&last_pos)
        .and_then(|v| v.as_object())
        .map(|obj| {
            obj.iter()
                .map(|(spot, fid)| {
                    (
                        spot.clone(),
                        fid.as_str().unwrap_or("").to_string(),
                    )
                })
                .collect()
        })
        .unwrap_or_default();

    for (_spot, feature_id) in spots {
        if checked_features.contains(&feature_id) {
            continue;
        }
        checked_features.insert(feature_id.clone());

        let feature = match game_data["features"].get(&feature_id) {
            Some(f) => f.clone(),
            None => continue,
        };

        if feature.get("is_complete").and_then(|v| v.as_bool()).unwrap_or(false) {
            continue;
        }

        if !is_feature_complete(game_data, &feature) {
            continue;
        }

        // Mark complete
        game_data["features"][&feature_id]["is_complete"] = serde_json::json!(true);

        let feature = &game_data["features"][&feature_id];
        let point_awards = score_completed_feature(feature);

        for (pid, points) in &point_awards {
            *scores.entry(pid.clone()).or_insert(0) += points;
            events.push(Event {
                event_type: "feature_scored".into(),
                player_id: Some(pid.clone()),
                payload: serde_json::json!({
                    "feature_id": feature_id,
                    "feature_type": game_data["features"][&feature_id]["feature_type"],
                    "points": points,
                    "tiles": game_data["features"][&feature_id]["tiles"],
                }),
            });
        }

        // Return meeples
        let meeple_events = return_meeples(game_data, &feature_id);
        events.extend(meeple_events);
    }

    // Check monasteries near the placed tile
    let (monastery_events, monastery_scores) =
        check_monastery_completion(game_data, &last_pos);
    events.extend(monastery_events);
    for (pid, points) in &monastery_scores {
        *scores.entry(pid.clone()).or_insert(0) += points;
    }

    game_data["scores"] = serde_json::json!(scores);

    // Advance to next non-forfeited player
    let player_index = phase.metadata["player_index"].as_u64().unwrap_or(0) as usize;
    let next_index = find_next_player(game_data, players, player_index);

    let next_phase = Phase {
        name: "draw_tile".into(),
        auto_resolve: true,
        concurrent_mode: None,
        expected_actions: vec![],
        metadata: serde_json::json!({"player_index": next_index}),
    };

    TransitionResult {
        game_data: game_data.clone(),
        events,
        next_phase,
        scores: float_scores(&game_data["scores"]),
        game_over: None,
    }
}

fn apply_end_game_scoring(
    game_data: &mut serde_json::Value,
    _phase: &Phase,
    _players: &[Player],
) -> TransitionResult {
    let mut events: Vec<Event> = Vec::new();
    let mut scores: HashMap<String, i64> = HashMap::new();

    if let Some(obj) = game_data["scores"].as_object() {
        for (k, v) in obj {
            scores.insert(k.clone(), v.as_i64().unwrap_or(0));
        }
    }

    let (end_scores, breakdown) = score_end_game(game_data);
    game_data["end_game_breakdown"] = serde_json::json!(breakdown);

    for (pid, points) in &end_scores {
        *scores.entry(pid.clone()).or_insert(0) += points;
        events.push(Event {
            event_type: "end_game_points".into(),
            player_id: Some(pid.clone()),
            payload: serde_json::json!({
                "points": points,
                "breakdown": breakdown.get(pid).cloned().unwrap_or_default(),
            }),
        });
    }

    game_data["scores"] = serde_json::json!(scores);

    let max_score = scores.values().copied().max().unwrap_or(0);
    let winners: Vec<String> = scores
        .iter()
        .filter(|(_, &s)| s == max_score)
        .map(|(pid, _)| pid.clone())
        .collect();

    let final_scores = float_scores(&game_data["scores"]);

    TransitionResult {
        game_data: game_data.clone(),
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

// ------------------------------------------------------------------ //
//  Valid actions helpers
// ------------------------------------------------------------------ //

fn get_valid_tile_placements(
    game_data: &serde_json::Value,
    player_id: &str,
) -> Vec<serde_json::Value> {
    let current_tile = match game_data["current_tile"].as_str() {
        Some(t) => t,
        None => return vec![],
    };

    let board_tiles = parse_board_tiles(&game_data["board"]["tiles"]);
    let open_positions: Vec<String> = game_data["board"]["open_positions"]
        .as_array()
        .map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect())
        .unwrap_or_default();

    let has_meeples = game_data["meeple_supply"]
        .get(player_id)
        .and_then(|v| v.as_i64())
        .unwrap_or(0)
        > 0;

    let mut placements = Vec::new();

    for pos_key in &open_positions {
        let parts: Vec<&str> = pos_key.split(',').collect();
        if parts.len() != 2 {
            continue;
        }
        let x: i64 = parts[0].parse().unwrap_or(0);
        let y: i64 = parts[1].parse().unwrap_or(0);

        for rotation in [0u32, 90, 180, 270] {
            if can_place_tile(&board_tiles, current_tile, pos_key, rotation) {
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
                    "x": x,
                    "y": y,
                    "rotation": rotation,
                    "meeple_spots": meeple_spots,
                }));
            }
        }
    }

    placements
}

fn get_valid_meeple_placements(
    game_data: &serde_json::Value,
    player_id: &str,
) -> Vec<serde_json::Value> {
    let last_pos = match game_data["last_placed_position"].as_str() {
        Some(p) => p,
        None => return vec![serde_json::json!({"skip": true})],
    };

    let placed_tile = &game_data["board"]["tiles"][last_pos];
    let tile_type_id = placed_tile["tile_type_id"].as_str().unwrap_or("");
    let rotation = placed_tile["rotation"].as_u64().unwrap_or(0) as u32;

    let rotated_features = get_rotated_features(tile_type_id, rotation);
    let mut spots: Vec<serde_json::Value> = Vec::new();
    let mut seen_spots = std::collections::HashSet::new();

    for tile_feat in &rotated_features {
        for spot in &tile_feat.meeple_spots {
            if !seen_spots.insert(spot.clone()) {
                continue;
            }
            if can_place_meeple(game_data, player_id, last_pos, spot) {
                spots.push(serde_json::json!({"meeple_spot": spot}));
            }
        }
    }

    spots.push(serde_json::json!({"skip": true}));
    spots
}

// ------------------------------------------------------------------ //
//  Validation helpers
// ------------------------------------------------------------------ //

fn validate_place_tile(
    game_data: &serde_json::Value,
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
    let current_tile = match game_data["current_tile"].as_str() {
        Some(t) => t,
        None => return Some("No tile drawn".into()),
    };

    let board_tiles = parse_board_tiles(&game_data["board"]["tiles"]);
    if !can_place_tile(&board_tiles, current_tile, &pos_key, rotation) {
        return Some(format!(
            "Cannot place tile {} at {} with rotation {}",
            current_tile, pos_key, rotation
        ));
    }

    None
}

fn validate_place_meeple(
    game_data: &serde_json::Value,
    action: &Action,
) -> Option<String> {
    if action.payload.get("skip").and_then(|v| v.as_bool()).unwrap_or(false) {
        return None;
    }

    let spot = match action.payload.get("meeple_spot").and_then(|v| v.as_str()) {
        Some(s) => s,
        None => return Some("Missing meeple_spot in payload".into()),
    };

    let last_pos = match game_data["last_placed_position"].as_str() {
        Some(p) => p,
        None => return Some("No tile was placed this turn".into()),
    };

    if !can_place_meeple(game_data, &action.player_id, last_pos, spot) {
        return Some(format!(
            "Cannot place meeple on spot {} at {}",
            spot, last_pos
        ));
    }

    None
}

// ------------------------------------------------------------------ //
//  Utility helpers
// ------------------------------------------------------------------ //

fn parse_board_tiles(tiles_val: &serde_json::Value) -> HashMap<String, PlacedTile> {
    let mut board = HashMap::new();
    if let Some(obj) = tiles_val.as_object() {
        for (k, v) in obj {
            board.insert(
                k.clone(),
                PlacedTile {
                    tile_type_id: v["tile_type_id"].as_str().unwrap_or("").into(),
                    rotation: v["rotation"].as_u64().unwrap_or(0) as u32,
                },
            );
        }
    }
    board
}

fn float_scores(scores_val: &serde_json::Value) -> HashMap<String, f64> {
    let mut result = HashMap::new();
    if let Some(obj) = scores_val.as_object() {
        for (k, v) in obj {
            result.insert(k.clone(), v.as_f64().unwrap_or(0.0));
        }
    }
    result
}

fn find_next_player(
    game_data: &serde_json::Value,
    players: &[Player],
    current_index: usize,
) -> usize {
    let forfeited: std::collections::HashSet<String> = game_data
        .get("forfeited_players")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let num_players = players.len();
    let mut next = (current_index + 1) % num_players;
    for _ in 0..num_players {
        if !forfeited.contains(&players[next].player_id) {
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

        // Starting tile placed
        assert!(game_data["board"]["tiles"]["0,0"].is_object());
        assert_eq!(
            game_data["board"]["tiles"]["0,0"]["tile_type_id"].as_str().unwrap(),
            "D"
        );

        // Tile bag has tiles
        assert!(game_data["tile_bag"].as_array().unwrap().len() > 0);

        // Meeple supply
        assert_eq!(game_data["meeple_supply"]["p1"].as_i64().unwrap(), 7);
        assert_eq!(game_data["meeple_supply"]["p2"].as_i64().unwrap(), 7);

        // Scores start at 0
        assert_eq!(game_data["scores"]["p1"].as_i64().unwrap(), 0);

        // First phase is draw_tile
        assert_eq!(phase.name, "draw_tile");
        assert!(phase.auto_resolve);

        // Events: game_started + starting_tile_placed
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

        // Draw tile
        let draw_action = Action {
            action_type: "draw_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({}),
        };
        let result = plugin.apply_action(&game_data, &phase, &draw_action, &players);

        assert_eq!(result.next_phase.name, "place_tile");
        assert!(result.game_data["current_tile"].as_str().is_some());

        // Get valid actions for the drawn tile
        let valid = plugin.get_valid_actions(&result.game_data, &result.next_phase, "p1");
        assert!(!valid.is_empty(), "Should have valid placements");

        // Place the tile at the first valid position
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

        // Skip meeple
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

        // Score check (auto-resolve)
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
        // Player 2's turn
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
}
