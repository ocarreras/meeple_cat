from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient


@pytest.mark.asyncio
async def test_websocket_game_e2e(app):
    """End-to-end test of WebSocket game play with Carcassonne."""
    # Create HTTP client for setup (async for REST calls)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Get tokens for two players
        resp1 = await client.post("/api/v1/auth/token", json={"display_name": "Alice"})
        alice_data = resp1.json()
        alice_token = alice_data["token"]
        alice_id = alice_data["user_id"]

        resp2 = await client.post("/api/v1/auth/token", json={"display_name": "Bob"})
        bob_data = resp2.json()
        bob_token = bob_data["token"]
        bob_id = bob_data["user_id"]

        # Create a Carcassonne match with fixed seed
        create_resp = await client.post(
            "/api/v1/matches",
            json={
                "game_id": "carcassonne",
                "player_display_names": ["Alice", "Bob"],
                "config": {},
                "random_seed": 42,
            },
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert create_resp.status_code == 200
        match_id = create_resp.json()["match_id"]

    # Use Starlette's sync TestClient for WebSocket testing
    with TestClient(app) as tc:
        with tc.websocket_connect(
            f"/ws/game/{match_id}?token={alice_token}"
        ) as alice_ws:
            # Read CONNECTED message
            alice_connected = alice_ws.receive_json()
            assert alice_connected["type"] == "connected"
            assert alice_connected["payload"]["match_id"] == match_id
            assert alice_connected["payload"]["player_id"] == alice_id

            # Read initial STATE_UPDATE message
            alice_state1 = alice_ws.receive_json()
            assert alice_state1["type"] == "state_update"

            # Check initial state
            view = alice_state1["payload"]["view"]
            assert view["game_id"] == "carcassonne"
            assert view["status"] == "active"

            # The game should be in a phase expecting an action
            current_phase = view["current_phase"]
            assert current_phase["name"] in [
                "draw_tile", "place_tile", "place_meeple", "next_turn",
            ]

            # Test PING/PONG
            alice_ws.send_json({"type": "ping", "payload": {}})
            pong = alice_ws.receive_json()
            assert pong["type"] == "pong"

            # Play a move if we're in place_tile phase
            expected_actions = current_phase.get("expected_actions", [])
            if expected_actions:
                expected_player_id = expected_actions[0].get("player_id")

                # Only play if it's Alice's turn (the connected player)
                if expected_player_id == alice_id:
                    valid_actions = view.get("valid_actions", [])
                    if current_phase["name"] == "place_tile" and valid_actions:
                        # valid_actions are dicts like {"x": 0, "y": 1, "rotation": 0}
                        placement = valid_actions[0]
                        alice_ws.send_json({
                            "type": "action",
                            "payload": {
                                "action_type": "place_tile",
                                "payload": placement,
                            },
                        })

                        # Should receive state update(s) — auto-resolve
                        # may produce multiple updates
                        alice_update = alice_ws.receive_json()
                        assert alice_update["type"] == "state_update"


@pytest.mark.asyncio
async def test_websocket_invalid_token(app):
    """Test that invalid token is rejected."""
    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect("/ws/game/fake-match?token=invalid") as ws:
                pass


@pytest.mark.asyncio
async def test_websocket_match_not_found(app):
    """Test that connecting to non-existent match fails."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/token", json={"display_name": "Alice"})
        token = resp.json()["token"]

    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect(
                f"/ws/game/non-existent-match-id?token={token}"
            ) as ws:
                pass


@pytest.mark.asyncio
async def test_websocket_player_not_in_match(app):
    """Test that player not in match is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.post("/api/v1/auth/token", json={"display_name": "Alice"})
        alice_token = resp1.json()["token"]

        resp2 = await client.post("/api/v1/auth/token", json={"display_name": "Charlie"})
        charlie_token = resp2.json()["token"]

        # Create a match with Alice and Bob (not Charlie)
        create_resp = await client.post(
            "/api/v1/matches",
            json={
                "game_id": "carcassonne",
                "player_display_names": ["Alice", "Bob"],
                "random_seed": 42,
            },
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        match_id = create_resp.json()["match_id"]

    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect(
                f"/ws/game/{match_id}?token={charlie_token}"
            ) as ws:
                pass
