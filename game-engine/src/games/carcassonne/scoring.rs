//! Scoring logic for completed features and end-game scoring.
//! Mirrors backend/src/games/carcassonne/scoring.py.

use std::collections::HashMap;

use super::tiles::get_rotated_features;
use super::types::{CarcassonneState, Feature, FeatureType, Position};

/// Score a completed feature. Returns {player_id: points}.
pub fn score_completed_feature(feature: &Feature) -> HashMap<String, i64> {
    if feature.meeples.is_empty() {
        return HashMap::new();
    }

    // Count meeples per player
    let mut meeple_counts: HashMap<String, i64> = HashMap::new();
    for m in &feature.meeples {
        *meeple_counts.entry(m.player_id.clone()).or_insert(0) += 1;
    }

    let max_count = *meeple_counts.values().max().unwrap_or(&0);
    let winners: Vec<String> = meeple_counts
        .iter()
        .filter(|(_, &count)| count == max_count)
        .map(|(pid, _)| pid.clone())
        .collect();

    let tile_count = feature.tiles.len() as i64;

    let points = match feature.feature_type {
        FeatureType::City => tile_count * 2 + feature.pennants as i64 * 2,
        FeatureType::Road => tile_count,
        FeatureType::Monastery => 9,
        FeatureType::Field => return HashMap::new(),
    };

    winners.into_iter().map(|pid| (pid, points)).collect()
}

/// Score all incomplete features and fields at game end.
pub fn score_end_game(
    state: &CarcassonneState,
) -> (HashMap<String, i64>, HashMap<String, HashMap<String, i64>>) {
    let mut scores: HashMap<String, i64> = HashMap::new();
    let mut breakdown: HashMap<String, HashMap<String, i64>> = HashMap::new();

    for (feature_id, feature) in &state.features {
        if feature.is_complete {
            continue;
        }

        if feature.meeples.is_empty() {
            continue;
        }

        let mut meeple_counts: HashMap<String, i64> = HashMap::new();
        for m in &feature.meeples {
            *meeple_counts.entry(m.player_id.clone()).or_insert(0) += 1;
        }

        let max_count = *meeple_counts.values().max().unwrap_or(&0);
        let winners: Vec<String> = meeple_counts
            .iter()
            .filter(|(_, &count)| count == max_count)
            .map(|(pid, _)| pid.clone())
            .collect();

        let tile_count = feature.tiles.len() as i64;

        let (points, category) = match feature.feature_type {
            FeatureType::City => {
                (tile_count + feature.pennants as i64, "cities")
            }
            FeatureType::Road => (tile_count, "roads"),
            FeatureType::Monastery => {
                if feature.tiles.is_empty() {
                    (0, "monasteries")
                } else {
                    let pos = Position::from_key(&feature.tiles[0]);
                    let neighbors_present: i64 = pos
                        .all_surrounding()
                        .iter()
                        .filter(|p| state.board.tiles.contains_key(&(p.x, p.y)))
                        .count() as i64;
                    (1 + neighbors_present, "monasteries")
                }
            }
            FeatureType::Field => {
                let adjacent_cities =
                    get_adjacent_completed_cities(state, feature, feature_id);
                (adjacent_cities.len() as i64 * 3, "fields")
            }
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
pub(crate) fn get_adjacent_completed_cities(
    state: &CarcassonneState,
    field_feature: &Feature,
    field_feature_id: &str,
) -> Vec<String> {
    let mut adjacent_city_ids: Vec<String> = Vec::new();

    for tile_pos in &field_feature.tiles {
        let Some(spots) = state.tile_feature_map.get(tile_pos.as_str()) else {
            continue;
        };

        // Find which meeple spots on this tile belong to this field
        let field_spots: Vec<&str> = spots
            .iter()
            .filter(|(_, fid)| fid.as_str() == field_feature_id)
            .map(|(spot, _)| spot.as_str())
            .collect();

        if field_spots.is_empty() {
            continue;
        }

        let pos = Position::from_key(tile_pos);
        let Some(placed_tile) = state.board.tiles.get(&(pos.x, pos.y)) else {
            continue;
        };

        let rotated = get_rotated_features(placed_tile.tile_type_id, placed_tile.rotation);

        for tile_feat in rotated {
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
                let city_fid = match spots.get(city_spot.as_str()) {
                    Some(s) => s,
                    None => continue,
                };

                let Some(city_feature) = state.features.get(city_fid.as_str()) else {
                    continue;
                };

                if city_feature.is_complete && !adjacent_city_ids.contains(city_fid) {
                    adjacent_city_ids.push(city_fid.clone());
                }
            }
        }
    }

    adjacent_city_ids
}
