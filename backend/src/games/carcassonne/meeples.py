"""Meeple placement and return logic."""

from __future__ import annotations

from src.engine.models import Event


def can_place_meeple(
    game_data: dict,
    player_id: str,
    position_key: str,
    meeple_spot: str,
) -> bool:
    """Check if a meeple can be placed on this spot.

    Rules:
    1. Player has at least 1 available meeple
    2. The feature the spot belongs to has no meeples on it
    """
    # Player has meeples?
    if game_data["meeple_supply"].get(player_id, 0) <= 0:
        return False

    # Find the feature this spot belongs to
    tile_spots = game_data["tile_feature_map"].get(position_key, {})
    feature_id = tile_spots.get(meeple_spot)
    if feature_id is None:
        return False

    feature = game_data["features"].get(feature_id)
    if feature is None:
        return False

    # Feature already claimed?
    if feature.get("meeples"):
        return False

    return True


def return_meeples(game_data: dict, feature: dict) -> list[Event]:
    """Return meeples from a scored feature back to their owners.

    Modifies game_data["meeple_supply"] in place.
    Clears the feature's meeple list.

    Returns events for each returned meeple.
    """
    events: list[Event] = []

    for meeple in feature.get("meeples", []):
        player_id = meeple["player_id"]
        game_data["meeple_supply"][player_id] = (
            game_data["meeple_supply"].get(player_id, 0) + 1
        )
        events.append(Event(
            event_type="meeple_returned",
            player_id=player_id,
            payload={
                "position": meeple["position"],
                "spot": meeple["spot"],
            },
        ))

    feature["meeples"] = []
    return events
