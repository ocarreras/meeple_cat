//! Scoring logic for completed features and end-game scoring.
//! Mirrors backend/src/games/carcassonne/scoring.py.

use std::collections::HashMap;

use super::tiles::get_rotated_features;
use super::types::Position;

/// Score a completed feature. Returns {player_id: points}.
pub fn score_completed_feature(feature: &serde_json::Value) -> HashMap<String, i64> {
    let meeples = match feature.get("meeples").and_then(|v| v.as_array()) {
        Some(arr) if !arr.is_empty() => arr,
        _ => return HashMap::new(),
    };

    // Count meeples per player
    let mut meeple_counts: HashMap<String, i64> = HashMap::new();
    for m in meeples {
        if let Some(pid) = m.get("player_id").and_then(|v| v.as_str()) {
            *meeple_counts.entry(pid.to_string()).or_insert(0) += 1;
        }
    }

    let max_count = *meeple_counts.values().max().unwrap_or(&0);
    let winners: Vec<String> = meeple_counts
        .iter()
        .filter(|(_, &count)| count == max_count)
        .map(|(pid, _)| pid.clone())
        .collect();

    let ft = feature["feature_type"].as_str().unwrap_or("");
    let tiles = feature.get("tiles").and_then(|v| v.as_array());
    let tile_count = tiles.map(|t| t.len() as i64).unwrap_or(0);

    let points = match ft {
        "city" => tile_count * 2 + feature.get("pennants").and_then(|v| v.as_i64()).unwrap_or(0) * 2,
        "road" => tile_count,
        "monastery" => 9,
        _ => return HashMap::new(),
    };

    winners.into_iter().map(|pid| (pid, points)).collect()
}

/// Score all incomplete features and fields at game end.
pub fn score_end_game(
    game_data: &serde_json::Value,
) -> (HashMap<String, i64>, HashMap<String, HashMap<String, i64>>) {
    let mut scores: HashMap<String, i64> = HashMap::new();
    let mut breakdown: HashMap<String, HashMap<String, i64>> = HashMap::new();

    let features = match game_data.get("features").and_then(|v| v.as_object()) {
        Some(f) => f,
        None => return (scores, breakdown),
    };

    let board_tiles = &game_data["board"]["tiles"];

    for (feature_id, feature) in features {
        if feature.get("is_complete").and_then(|v| v.as_bool()).unwrap_or(false) {
            continue;
        }

        let meeples = match feature.get("meeples").and_then(|v| v.as_array()) {
            Some(arr) if !arr.is_empty() => arr,
            _ => continue,
        };

        let mut meeple_counts: HashMap<String, i64> = HashMap::new();
        for m in meeples {
            if let Some(pid) = m.get("player_id").and_then(|v| v.as_str()) {
                *meeple_counts.entry(pid.to_string()).or_insert(0) += 1;
            }
        }

        let max_count = *meeple_counts.values().max().unwrap_or(&0);
        let winners: Vec<String> = meeple_counts
            .iter()
            .filter(|(_, &count)| count == max_count)
            .map(|(pid, _)| pid.clone())
            .collect();

        let ft = feature["feature_type"].as_str().unwrap_or("");
        let tiles = feature.get("tiles").and_then(|v| v.as_array());
        let tile_count = tiles.map(|t| t.len() as i64).unwrap_or(0);

        let (points, category) = match ft {
            "city" => {
                let pennants = feature.get("pennants").and_then(|v| v.as_i64()).unwrap_or(0);
                (tile_count + pennants, "cities")
            }
            "road" => (tile_count, "roads"),
            "monastery" => {
                if let Some(tiles_arr) = tiles {
                    if tiles_arr.is_empty() {
                        (0, "monasteries")
                    } else {
                        let pos = Position::from_key(tiles_arr[0].as_str().unwrap());
                        let neighbors_present: i64 = pos
                            .all_surrounding()
                            .iter()
                            .filter(|p| board_tiles.get(&p.to_key()).is_some())
                            .count() as i64;
                        (1 + neighbors_present, "monasteries")
                    }
                } else {
                    (0, "monasteries")
                }
            }
            "field" => {
                let adjacent_cities =
                    get_adjacent_completed_cities(game_data, feature, feature_id);
                (adjacent_cities.len() as i64 * 3, "fields")
            }
            _ => continue,
        };

        for pid in &winners {
            *scores.entry(pid.clone()).or_insert(0) += points;
            let player_breakdown = breakdown
                .entry(pid.clone())
                .or_insert_with(|| {
                    let mut m = HashMap::new();
                    m.insert("fields".into(), 0);
                    m.insert("roads".into(), 0);
                    m.insert("cities".into(), 0);
                    m.insert("monasteries".into(), 0);
                    m
                });
            *player_breakdown.entry(category.into()).or_insert(0) += points;
        }
    }

    (scores, breakdown)
}

/// Find all completed cities that border a field feature.
fn get_adjacent_completed_cities(
    game_data: &serde_json::Value,
    field_feature: &serde_json::Value,
    field_feature_id: &str,
) -> Vec<String> {
    let features = &game_data["features"];
    let tile_feature_map = &game_data["tile_feature_map"];
    let board_tiles = &game_data["board"]["tiles"];

    let mut adjacent_city_ids: Vec<String> = Vec::new();

    let tiles = match field_feature.get("tiles").and_then(|v| v.as_array()) {
        Some(arr) => arr,
        None => return adjacent_city_ids,
    };

    for tile_pos_val in tiles {
        let tile_pos = match tile_pos_val.as_str() {
            Some(s) => s,
            None => continue,
        };

        let Some(spots) = tile_feature_map.get(tile_pos).and_then(|v| v.as_object()) else {
            continue;
        };

        // Find which meeple spots on this tile belong to this field
        let field_spots: Vec<&str> = spots
            .iter()
            .filter(|(_, fid)| fid.as_str() == Some(field_feature_id))
            .map(|(spot, _)| spot.as_str())
            .collect();

        if field_spots.is_empty() {
            continue;
        }

        // Look up placed tile to get tile type and rotation
        let Some(placed_tile) = board_tiles.get(tile_pos) else {
            continue;
        };
        let tile_type_id = placed_tile["tile_type_id"].as_str().unwrap_or("");
        let rotation = placed_tile["rotation"].as_u64().unwrap_or(0) as u32;

        let rotated = get_rotated_features(tile_type_id, rotation);

        for tile_feat in &rotated {
            let matching: Vec<&str> = tile_feat
                .meeple_spots
                .iter()
                .filter(|s| field_spots.contains(&s.as_str()))
                .map(|s| s.as_str())
                .collect();

            if matching.is_empty() {
                continue;
            }

            for city_spot in &tile_feat.adjacent_cities {
                let city_fid = match tile_feature_map
                    .get(tile_pos)
                    .and_then(|v| v.get(city_spot.as_str()))
                    .and_then(|v| v.as_str())
                {
                    Some(s) => s,
                    None => continue,
                };

                let Some(city_feature) = features.get(city_fid) else {
                    continue;
                };

                if city_feature
                    .get("is_complete")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false)
                    && !adjacent_city_ids.contains(&city_fid.to_string())
                {
                    adjacent_city_ids.push(city_fid.to_string());
                }
            }
        }
    }

    adjacent_city_ids
}
