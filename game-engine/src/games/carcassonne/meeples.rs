//! Meeple placement and return logic.
//! Mirrors backend/src/games/carcassonne/meeples.py.

use crate::engine::models::Event;
use super::types::{CarcassonneState, PlacedMeeple};

/// Check if a meeple can be placed on this spot.
///
/// Rules:
/// 1. Player has at least 1 available meeple
/// 2. The feature the spot belongs to has no meeples on it
pub fn can_place_meeple(
    state: &CarcassonneState,
    player_id: &str,
    position_key: &str,
    meeple_spot: &str,
) -> bool {
    let supply = state.meeple_supply.get(player_id).copied().unwrap_or(0);
    if supply <= 0 {
        return false;
    }

    let feature_id = match state
        .tile_feature_map
        .get(position_key)
        .and_then(|spots| spots.get(meeple_spot))
    {
        Some(fid) => fid,
        None => return false,
    };

    let feature = match state.features.get(feature_id) {
        Some(f) => f,
        None => return false,
    };

    feature.meeples.is_empty()
}

/// Return meeples from a scored feature back to their owners.
/// Mutates state in place and clears the feature's meeple list.
pub fn return_meeples(
    state: &mut CarcassonneState,
    feature_id: &str,
) -> Vec<Event> {
    let mut events = Vec::new();

    let meeples: Vec<PlacedMeeple> = match state.features.get(feature_id) {
        Some(f) => f.meeples.clone(),
        None => return events,
    };

    for meeple in &meeples {
        // Increment meeple supply
        if let Some(supply) = state.meeple_supply.get_mut(&meeple.player_id) {
            *supply += 1;
        }

        events.push(Event {
            event_type: "meeple_returned".to_string(),
            player_id: Some(meeple.player_id.clone()),
            payload: serde_json::json!({
                "position": meeple.position,
                "spot": meeple.spot,
            }),
        });
    }

    // Clear meeples from feature
    if let Some(feature) = state.features.get_mut(feature_id) {
        feature.meeples.clear();
    }

    events
}
