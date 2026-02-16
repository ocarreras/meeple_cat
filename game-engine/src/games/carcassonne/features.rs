//! Feature tracking: creation, merging, and completion detection.
//! Mirrors backend/src/games/carcassonne/features.py.

use std::collections::HashMap;

use uuid::Uuid;

use crate::engine::models::Event;
use super::tiles::get_rotated_features;
use super::types::*;

/// Get the opposite edge identifier. Handles compound edges like "E:N" → "W:N".
fn opposite_edge(edge: &str) -> String {
    if let Some((direction, side)) = edge.split_once(':') {
        format!("{}:{}", opposite_direction(direction), side)
    } else {
        opposite_direction(edge).to_string()
    }
}

/// Get the cardinal direction from an edge (simple or compound).
fn edge_direction(edge: &str) -> &str {
    edge.split(':').next().unwrap()
}

/// Create features for a single tile (used for the starting tile).
pub fn initialize_features_from_tile(
    tile_type_id: &str,
    position_key: &str,
    rotation: u32,
) -> (HashMap<String, serde_json::Value>, HashMap<String, HashMap<String, String>>) {
    let mut features: HashMap<String, serde_json::Value> = HashMap::new();
    let mut tile_feature_map: HashMap<String, HashMap<String, String>> = HashMap::new();
    tile_feature_map.insert(position_key.to_string(), HashMap::new());

    let rotated_features = get_rotated_features(tile_type_id, rotation);

    for tile_feat in &rotated_features {
        let feature_id = Uuid::new_v4().to_string();

        let open_edges: Vec<[String; 2]> = tile_feat
            .edges
            .iter()
            .map(|e| [position_key.to_string(), e.clone()])
            .collect();

        let pennants: u32 = if tile_feat.has_pennant { 1 } else { 0 };

        let feature = Feature {
            feature_id: feature_id.clone(),
            feature_type: tile_feat.feature_type,
            tiles: vec![position_key.to_string()],
            meeples: vec![],
            is_complete: false,
            pennants,
            open_edges,
        };
        features.insert(feature_id.clone(), serde_json::to_value(&feature).unwrap());

        let spots = tile_feature_map.get_mut(position_key).unwrap();
        for spot in &tile_feat.meeple_spots {
            spots.insert(spot.clone(), feature_id.clone());
        }
    }

    (features, tile_feature_map)
}

/// Place a tile's features on the board and merge with adjacent features.
/// Modifies game_data in place. Returns merge events.
pub fn create_and_merge_features(
    game_data: &mut serde_json::Value,
    tile_type_id: &str,
    position_key: &str,
    rotation: u32,
) -> Vec<Event> {
    let mut events = Vec::new();

    let rotated_features = get_rotated_features(tile_type_id, rotation);

    // Initialize the feature map for this tile position
    game_data["tile_feature_map"][position_key] = serde_json::json!({});

    // Map from edge direction to the feature that touches that edge
    let mut edge_to_feature: Vec<(String, String)> = Vec::new();
    let mut new_feature_ids: Vec<String> = Vec::new();

    // Step 1: Create features for the new tile
    for tile_feat in &rotated_features {
        let feature_id = Uuid::new_v4().to_string();

        let open_edges: Vec<serde_json::Value> = tile_feat
            .edges
            .iter()
            .map(|e| serde_json::json!([position_key, e]))
            .collect();

        let pennants: u32 = if tile_feat.has_pennant { 1 } else { 0 };

        let feature = serde_json::json!({
            "feature_id": feature_id,
            "feature_type": tile_feat.feature_type,
            "tiles": [position_key],
            "meeples": [],
            "is_complete": false,
            "pennants": pennants,
            "open_edges": open_edges,
        });

        game_data["features"][&feature_id] = feature;
        new_feature_ids.push(feature_id.clone());

        for spot in &tile_feat.meeple_spots {
            game_data["tile_feature_map"][position_key][spot.as_str()] =
                serde_json::json!(feature_id);
        }

        for edge_dir in &tile_feat.edges {
            edge_to_feature.push((edge_dir.clone(), feature_id.clone()));
        }
    }

    // Step 2: Merge with adjacent tiles
    let pos = Position::from_key(position_key);

    for i in 0..edge_to_feature.len() {
        let (edge_key, mut our_feature_id) = edge_to_feature[i].clone();
        let direction = edge_direction(&edge_key);
        let neighbor_pos = pos.neighbor(direction);
        let neighbor_key = neighbor_pos.to_key();

        // Check if neighbor tile exists
        if game_data["board"]["tiles"].get(&neighbor_key).is_none() {
            continue;
        }

        // Resolve to current feature (may have been merged)
        our_feature_id = resolve_feature_id(game_data, &our_feature_id);

        let opp_edge = opposite_edge(&edge_key);

        // Find adjacent feature
        let adj_feature_id = match find_feature_at_edge(game_data, &neighbor_key, &opp_edge) {
            Some(id) => resolve_feature_id(game_data, &id),
            None => continue,
        };

        if our_feature_id == adj_feature_id {
            // Already same feature — just remove connecting open edges
            remove_open_edge(game_data, &our_feature_id, position_key, &edge_key);
            remove_open_edge(game_data, &our_feature_id, &neighbor_key, &opp_edge);
            continue;
        }

        // Verify same feature type
        let our_type = game_data["features"][&our_feature_id]["feature_type"].as_str().unwrap_or("");
        let adj_type = game_data["features"][&adj_feature_id]["feature_type"].as_str().unwrap_or("");
        if our_type != adj_type {
            continue;
        }

        // Merge: absorb adj into ours
        let merged_id = merge_features(game_data, &our_feature_id, &adj_feature_id);

        remove_open_edge(game_data, &merged_id, position_key, &edge_key);
        remove_open_edge(game_data, &merged_id, &neighbor_key, &opp_edge);

        // Update edge_to_feature for subsequent merges
        for (_, fid) in edge_to_feature.iter_mut() {
            if *fid == adj_feature_id || *fid == our_feature_id {
                *fid = merged_id.clone();
            }
        }

        let merged_type = game_data["features"][&merged_id]["feature_type"].clone();
        events.push(Event {
            event_type: "feature_merged".to_string(),
            player_id: None,
            payload: serde_json::json!({
                "surviving_feature": merged_id,
                "merged_feature": if merged_id == our_feature_id { &adj_feature_id } else { &our_feature_id },
                "feature_type": merged_type,
            }),
        });
    }

    events
}

/// Resolve a feature ID that may have been merged into another.
fn resolve_feature_id(game_data: &serde_json::Value, feature_id: &str) -> String {
    if game_data["features"].get(feature_id).is_some() {
        return feature_id.to_string();
    }
    // Search for which feature absorbed this one
    if let Some(features) = game_data["features"].as_object() {
        for (fid, feat) in features {
            if let Some(merged_from) = feat.get("_merged_from") {
                if let Some(arr) = merged_from.as_array() {
                    for v in arr {
                        if v.as_str() == Some(feature_id) {
                            return fid.clone();
                        }
                    }
                }
            }
        }
    }
    feature_id.to_string()
}

/// Find the feature ID that touches a specific edge on a tile.
fn find_feature_at_edge(
    game_data: &serde_json::Value,
    position_key: &str,
    direction: &str,
) -> Option<String> {
    let tfm = game_data["tile_feature_map"].get(position_key)?;
    let spots = tfm.as_object()?;

    for (_spot, fid_val) in spots {
        let fid = fid_val.as_str()?;
        let feat = game_data["features"].get(fid)?;
        if let Some(open_edges) = feat.get("open_edges") {
            if let Some(arr) = open_edges.as_array() {
                for oe in arr {
                    if let Some(oe_arr) = oe.as_array() {
                        if oe_arr.len() == 2
                            && oe_arr[0].as_str() == Some(position_key)
                            && oe_arr[1].as_str() == Some(direction)
                        {
                            return Some(fid.to_string());
                        }
                    }
                }
            }
        }
    }
    None
}

/// Merge feature_b into feature_a. Returns the surviving feature ID.
fn merge_features(
    game_data: &mut serde_json::Value,
    feature_a_id: &str,
    feature_b_id: &str,
) -> String {
    // Read feature_b data before removing it
    let b = game_data["features"][feature_b_id].clone();

    let a = &mut game_data["features"][feature_a_id];

    // Combine tiles (deduplicate)
    let mut tiles: Vec<String> = Vec::new();
    if let Some(arr) = a["tiles"].as_array() {
        for v in arr { if let Some(s) = v.as_str() { tiles.push(s.to_string()); } }
    }
    if let Some(arr) = b["tiles"].as_array() {
        for v in arr {
            if let Some(s) = v.as_str() {
                if !tiles.contains(&s.to_string()) {
                    tiles.push(s.to_string());
                }
            }
        }
    }
    a["tiles"] = serde_json::json!(tiles);

    // Combine meeples
    let mut meeples: Vec<serde_json::Value> = Vec::new();
    if let Some(arr) = a["meeples"].as_array() { meeples.extend(arr.iter().cloned()); }
    if let Some(arr) = b["meeples"].as_array() { meeples.extend(arr.iter().cloned()); }
    a["meeples"] = serde_json::json!(meeples);

    // Combine pennants
    let pa = a["pennants"].as_u64().unwrap_or(0);
    let pb = b["pennants"].as_u64().unwrap_or(0);
    a["pennants"] = serde_json::json!(pa + pb);

    // Combine open edges
    let mut open_edges: Vec<serde_json::Value> = Vec::new();
    if let Some(arr) = a["open_edges"].as_array() { open_edges.extend(arr.iter().cloned()); }
    if let Some(arr) = b["open_edges"].as_array() { open_edges.extend(arr.iter().cloned()); }
    a["open_edges"] = serde_json::json!(open_edges);

    // Track merged IDs
    let mut merged_from: Vec<String> = Vec::new();
    if let Some(arr) = a.get("_merged_from").and_then(|v| v.as_array()) {
        for v in arr { if let Some(s) = v.as_str() { merged_from.push(s.to_string()); } }
    }
    merged_from.push(feature_b_id.to_string());
    if let Some(arr) = b.get("_merged_from").and_then(|v| v.as_array()) {
        for v in arr { if let Some(s) = v.as_str() { merged_from.push(s.to_string()); } }
    }
    a["_merged_from"] = serde_json::json!(merged_from);

    // Update tile_feature_map: all references to feature_b → feature_a
    if let Some(tfm) = game_data["tile_feature_map"].as_object_mut() {
        for (_pos, spots) in tfm.iter_mut() {
            if let Some(spots_obj) = spots.as_object_mut() {
                for (_spot, fid) in spots_obj.iter_mut() {
                    if fid.as_str() == Some(feature_b_id) {
                        *fid = serde_json::json!(feature_a_id);
                    }
                }
            }
        }
    }

    // Remove feature_b
    if let Some(features) = game_data["features"].as_object_mut() {
        features.remove(feature_b_id);
    }

    feature_a_id.to_string()
}

/// Remove a specific open edge from a feature.
fn remove_open_edge(
    game_data: &mut serde_json::Value,
    feature_id: &str,
    position_key: &str,
    direction: &str,
) {
    if let Some(feat) = game_data["features"].get_mut(feature_id) {
        if let Some(open_edges) = feat.get_mut("open_edges") {
            if let Some(arr) = open_edges.as_array() {
                let filtered: Vec<serde_json::Value> = arr
                    .iter()
                    .filter(|oe| {
                        if let Some(oe_arr) = oe.as_array() {
                            !(oe_arr.len() == 2
                                && oe_arr[0].as_str() == Some(position_key)
                                && oe_arr[1].as_str() == Some(direction))
                        } else {
                            true
                        }
                    })
                    .cloned()
                    .collect();
                *open_edges = serde_json::json!(filtered);
            }
        }
    }
}

/// Check if a feature is complete.
pub fn is_feature_complete(game_data: &serde_json::Value, feature: &serde_json::Value) -> bool {
    let ft = feature["feature_type"].as_str().unwrap_or("");

    if ft == "field" {
        return false;
    }

    if ft == "monastery" {
        let tiles = match feature["tiles"].as_array() {
            Some(arr) => arr,
            None => return false,
        };
        if tiles.is_empty() {
            return false;
        }
        let pos = Position::from_key(tiles[0].as_str().unwrap());
        let board_tiles = &game_data["board"]["tiles"];
        for surrounding in pos.all_surrounding() {
            if board_tiles.get(&surrounding.to_key()).is_none() {
                return false;
            }
        }
        return true;
    }

    // City or Road: complete when no open edges
    match feature.get("open_edges").and_then(|v| v.as_array()) {
        Some(arr) => arr.is_empty(),
        None => true,
    }
}

/// Check if any monasteries near the placed tile are now complete.
pub fn check_monastery_completion(
    game_data: &mut serde_json::Value,
    position_key: &str,
) -> (Vec<Event>, HashMap<String, i64>) {
    use super::scoring::score_completed_feature;
    use super::meeples::return_meeples;

    let mut events = Vec::new();
    let mut scores: HashMap<String, i64> = HashMap::new();

    let pos = Position::from_key(position_key);
    let mut positions_to_check = vec![pos];
    positions_to_check.extend(pos.all_surrounding());

    for check_pos in positions_to_check {
        let check_key = check_pos.to_key();

        // Collect monastery feature IDs at this position
        let monastery_ids: Vec<String> = {
            let tfm = &game_data["tile_feature_map"];
            let Some(spots) = tfm.get(&check_key).and_then(|v| v.as_object()) else {
                continue;
            };
            spots
                .values()
                .filter_map(|fid_val| {
                    let fid = fid_val.as_str()?;
                    let feat = game_data["features"].get(fid)?;
                    if feat["feature_type"].as_str() == Some("monastery")
                        && !feat["is_complete"].as_bool().unwrap_or(false)
                    {
                        Some(fid.to_string())
                    } else {
                        None
                    }
                })
                .collect()
        };

        for feature_id in monastery_ids {
            let feature = &game_data["features"][&feature_id];
            if !is_feature_complete(game_data, feature) {
                continue;
            }

            // Mark complete
            game_data["features"][&feature_id]["is_complete"] = serde_json::json!(true);

            let feature = &game_data["features"][&feature_id];
            let point_awards = score_completed_feature(feature);

            for (pid, points) in &point_awards {
                *scores.entry(pid.clone()).or_insert(0) += points;
                events.push(Event {
                    event_type: "feature_scored".to_string(),
                    player_id: Some(pid.clone()),
                    payload: serde_json::json!({
                        "feature_id": feature_id,
                        "feature_type": "monastery",
                        "points": points,
                        "tiles": game_data["features"][&feature_id]["tiles"],
                    }),
                });
            }

            // Return meeples
            let meeple_events = return_meeples(game_data, &feature_id);
            events.extend(meeple_events);
        }
    }

    (events, scores)
}
