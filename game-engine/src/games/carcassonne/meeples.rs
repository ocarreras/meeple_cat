//! Meeple placement and return logic.
//! Mirrors backend/src/games/carcassonne/meeples.py.

use crate::engine::models::Event;

/// Check if a meeple can be placed on this spot.
///
/// Rules:
/// 1. Player has at least 1 available meeple
/// 2. The feature the spot belongs to has no meeples on it
pub fn can_place_meeple(
    game_data: &serde_json::Value,
    player_id: &str,
    position_key: &str,
    meeple_spot: &str,
) -> bool {
    // Player has meeples?
    let supply = game_data["meeple_supply"]
        .get(player_id)
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    if supply <= 0 {
        return false;
    }

    // Find the feature this spot belongs to
    let feature_id = match game_data["tile_feature_map"]
        .get(position_key)
        .and_then(|v| v.get(meeple_spot))
        .and_then(|v| v.as_str())
    {
        Some(fid) => fid,
        None => return false,
    };

    let feature = match game_data["features"].get(feature_id) {
        Some(f) => f,
        None => return false,
    };

    // Feature already claimed?
    if let Some(meeples) = feature.get("meeples").and_then(|v| v.as_array()) {
        if !meeples.is_empty() {
            return false;
        }
    }

    true
}

/// Return meeples from a scored feature back to their owners.
/// Modifies game_data in place and clears the feature's meeple list.
pub fn return_meeples(
    game_data: &mut serde_json::Value,
    feature_id: &str,
) -> Vec<Event> {
    let mut events = Vec::new();

    // Read meeples before clearing
    let meeples: Vec<serde_json::Value> = game_data["features"][feature_id]
        .get("meeples")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    for meeple in &meeples {
        let player_id = meeple["player_id"].as_str().unwrap_or("").to_string();
        let position = meeple["position"].as_str().unwrap_or("").to_string();
        let spot = meeple["spot"].as_str().unwrap_or("").to_string();

        // Increment meeple supply
        let current = game_data["meeple_supply"]
            .get(&player_id)
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        game_data["meeple_supply"][&player_id] = serde_json::json!(current + 1);

        events.push(Event {
            event_type: "meeple_returned".to_string(),
            player_id: Some(player_id),
            payload: serde_json::json!({
                "position": position,
                "spot": spot,
            }),
        });
    }

    // Clear meeples from feature
    game_data["features"][feature_id]["meeples"] = serde_json::json!([]);

    events
}
