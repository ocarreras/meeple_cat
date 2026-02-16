//! Feature tracking: creation, merging, and completion detection.
//! Mirrors backend/src/games/carcassonne/features.py.

use std::collections::HashMap;

use crate::engine::models::Event;
use super::tiles::get_rotated_features_by_name;
use super::types::*;

/// Generate a sequential feature ID and increment the counter.
fn next_feature_id(state: &mut CarcassonneState) -> String {
    let id = state.next_feature_id;
    state.next_feature_id += 1;
    format!("f{}", id)
}

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
    feature_id_counter: &mut u64,
) -> (HashMap<String, Feature>, HashMap<String, HashMap<String, String>>) {
    let mut features: HashMap<String, Feature> = HashMap::new();
    let mut tile_feature_map: HashMap<String, HashMap<String, String>> = HashMap::new();
    tile_feature_map.insert(position_key.to_string(), HashMap::new());

    let rotated_features = get_rotated_features_by_name(tile_type_id, rotation);

    for tile_feat in rotated_features {
        let feature_id = {
            let id = *feature_id_counter;
            *feature_id_counter += 1;
            format!("f{}", id)
        };

        let open_edges: Vec<[String; 2]> = tile_feat
            .edges
            .iter()
            .map(|e| [position_key.to_string(), e.to_string()])
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
            merged_from: vec![],
        };
        features.insert(feature_id.clone(), feature);

        let spots = tile_feature_map.get_mut(position_key).unwrap();
        for spot in &tile_feat.meeple_spots {
            spots.insert(spot.to_string(), feature_id.clone());
        }
    }

    (features, tile_feature_map)
}

/// Place a tile's features on the board and merge with adjacent features.
/// Modifies state in place. Returns merge events.
pub fn create_and_merge_features(
    state: &mut CarcassonneState,
    tile_type_id: &str,
    position_key: &str,
    rotation: u32,
) -> Vec<Event> {
    let mut events = Vec::new();

    let rotated_features = get_rotated_features_by_name(tile_type_id, rotation);

    // Initialize the feature map for this tile position
    state.tile_feature_map.insert(position_key.to_string(), HashMap::new());

    // Map from edge direction to the feature that touches that edge
    let mut edge_to_feature: Vec<(String, String)> = Vec::new();

    // Step 1: Create features for the new tile
    for tile_feat in rotated_features {
        let feature_id = next_feature_id(state);

        let open_edges: Vec<[String; 2]> = tile_feat
            .edges
            .iter()
            .map(|e| [position_key.to_string(), e.to_string()])
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
            merged_from: vec![],
        };

        state.features.insert(feature_id.clone(), feature);

        if let Some(spots) = state.tile_feature_map.get_mut(position_key) {
            for spot in &tile_feat.meeple_spots {
                spots.insert(spot.to_string(), feature_id.clone());
            }
        }

        for edge_dir in &tile_feat.edges {
            edge_to_feature.push((edge_dir.to_string(), feature_id.clone()));
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
        if !state.board.tiles.contains_key(&(neighbor_pos.x, neighbor_pos.y)) {
            continue;
        }

        // Resolve to current feature (may have been merged)
        our_feature_id = resolve_feature_id(state, &our_feature_id);

        let opp_edge = opposite_edge(&edge_key);

        // Find adjacent feature
        let adj_feature_id = match find_feature_at_edge(state, &neighbor_key, &opp_edge) {
            Some(id) => resolve_feature_id(state, &id),
            None => continue,
        };

        if our_feature_id == adj_feature_id {
            // Already same feature — just remove connecting open edges
            remove_open_edge(state, &our_feature_id, position_key, &edge_key);
            remove_open_edge(state, &our_feature_id, &neighbor_key, &opp_edge);
            continue;
        }

        // Verify same feature type
        let our_type = state.features.get(&our_feature_id).map(|f| f.feature_type);
        let adj_type = state.features.get(&adj_feature_id).map(|f| f.feature_type);
        if our_type != adj_type {
            continue;
        }

        // Merge: absorb adj into ours
        let merged_id = merge_features(state, &our_feature_id, &adj_feature_id);

        remove_open_edge(state, &merged_id, position_key, &edge_key);
        remove_open_edge(state, &merged_id, &neighbor_key, &opp_edge);

        // Update edge_to_feature for subsequent merges
        for (_, fid) in edge_to_feature.iter_mut() {
            if *fid == adj_feature_id || *fid == our_feature_id {
                *fid = merged_id.clone();
            }
        }

        let merged_type = state.features.get(&merged_id).map(|f| f.feature_type);
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
/// Uses the redirect table for O(1) lookup instead of O(n*m) linear scan.
fn resolve_feature_id(state: &CarcassonneState, feature_id: &str) -> String {
    if state.features.contains_key(feature_id) {
        return feature_id.to_string();
    }
    // Check redirect table (populated during merges)
    if let Some(redirect) = state.feature_redirects.get(feature_id) {
        // Follow chain in case of transitive merges
        return resolve_feature_id(state, redirect);
    }
    feature_id.to_string()
}

/// Find the feature ID that touches a specific edge on a tile.
fn find_feature_at_edge(
    state: &CarcassonneState,
    position_key: &str,
    direction: &str,
) -> Option<String> {
    let spots = state.tile_feature_map.get(position_key)?;

    for (_spot, fid) in spots {
        let feat = state.features.get(fid)?;
        for oe in &feat.open_edges {
            if oe[0] == position_key && oe[1] == direction {
                return Some(fid.clone());
            }
        }
    }
    None
}

/// Merge feature_b into feature_a. Returns the surviving feature ID.
fn merge_features(
    state: &mut CarcassonneState,
    feature_a_id: &str,
    feature_b_id: &str,
) -> String {
    // Read feature_b data before removing it
    let b = match state.features.remove(feature_b_id) {
        Some(f) => f,
        None => return feature_a_id.to_string(),
    };

    // Populate redirect table: feature_b → feature_a
    state.feature_redirects.insert(feature_b_id.to_string(), feature_a_id.to_string());
    // Also redirect any IDs that previously pointed to feature_b
    for old_id in &b.merged_from {
        state.feature_redirects.insert(old_id.clone(), feature_a_id.to_string());
    }

    if let Some(a) = state.features.get_mut(feature_a_id) {
        // Combine tiles (deduplicate)
        for tile in &b.tiles {
            if !a.tiles.contains(tile) {
                a.tiles.push(tile.clone());
            }
        }

        // Combine meeples
        a.meeples.extend(b.meeples);

        // Combine pennants
        a.pennants += b.pennants;

        // Combine open edges
        a.open_edges.extend(b.open_edges);

        // Track merged IDs
        a.merged_from.push(feature_b_id.to_string());
        a.merged_from.extend(b.merged_from);
    }

    // Update tile_feature_map: all references to feature_b → feature_a
    for (_pos, spots) in state.tile_feature_map.iter_mut() {
        for (_spot, fid) in spots.iter_mut() {
            if fid == feature_b_id {
                *fid = feature_a_id.to_string();
            }
        }
    }

    feature_a_id.to_string()
}

/// Remove a specific open edge from a feature.
fn remove_open_edge(
    state: &mut CarcassonneState,
    feature_id: &str,
    position_key: &str,
    direction: &str,
) {
    if let Some(feat) = state.features.get_mut(feature_id) {
        feat.open_edges
            .retain(|oe| !(oe[0] == position_key && oe[1] == direction));
    }
}

/// Check if a feature is complete.
pub fn is_feature_complete(state: &CarcassonneState, feature: &Feature) -> bool {
    match feature.feature_type {
        FeatureType::Field => false,
        FeatureType::Monastery => {
            if feature.tiles.is_empty() {
                return false;
            }
            let pos = Position::from_key(&feature.tiles[0]);
            for surrounding in pos.all_surrounding() {
                if !state.board.tiles.contains_key(&(surrounding.x, surrounding.y)) {
                    return false;
                }
            }
            true
        }
        FeatureType::City | FeatureType::Road => feature.open_edges.is_empty(),
    }
}

/// Check if any monasteries near the placed tile are now complete.
pub fn check_monastery_completion(
    state: &mut CarcassonneState,
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
            let Some(spots) = state.tile_feature_map.get(&check_key) else {
                continue;
            };
            spots
                .values()
                .filter_map(|fid| {
                    let feat = state.features.get(fid)?;
                    if feat.feature_type == FeatureType::Monastery && !feat.is_complete {
                        Some(fid.clone())
                    } else {
                        None
                    }
                })
                .collect()
        };

        for feature_id in monastery_ids {
            let is_complete = {
                let Some(feature) = state.features.get(&feature_id) else {
                    continue;
                };
                is_feature_complete(state, feature)
            };

            if !is_complete {
                continue;
            }

            // Mark complete
            if let Some(feat) = state.features.get_mut(&feature_id) {
                feat.is_complete = true;
            }

            let point_awards = {
                let feature = &state.features[&feature_id];
                score_completed_feature(feature)
            };

            let tiles_clone = state.features[&feature_id].tiles.clone();

            for (pid, points) in &point_awards {
                *scores.entry(pid.clone()).or_insert(0) += points;
                events.push(Event {
                    event_type: "feature_scored".to_string(),
                    player_id: Some(pid.clone()),
                    payload: serde_json::json!({
                        "feature_id": feature_id,
                        "feature_type": "monastery",
                        "points": points,
                        "tiles": tiles_clone,
                    }),
                });
            }

            // Return meeples
            let meeple_events = return_meeples(state, &feature_id);
            events.extend(meeple_events);
        }
    }

    (events, scores)
}
