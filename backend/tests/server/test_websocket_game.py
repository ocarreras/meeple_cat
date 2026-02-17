from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient


@pytest.mark.slow
@pytest.mark.asyncio
async def test_websocket_game_e2e(app):
    """End-to-end test of WebSocket game play with MockPlugin."""
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

        # Create a match with MockPlugin
        create_resp = await client.post(
            "/api/v1/matches",
            json={
                "game_id": "mock-game",
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
            assert view["game_id"] == "mock-game"
            assert view["status"] == "active"

            # The game should be in a phase expecting an action
            current_phase = view["current_phase"]
            assert current_phase["name"] == "play"

            # Test PING/PONG
            alice_ws.send_json({"type": "ping", "payload": {}})
            pong = alice_ws.receive_json()
            assert pong["type"] == "pong"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_websocket_invalid_token(app):
    """Test that invalid token is rejected."""
    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect("/ws/game/fake-match?token=invalid") as ws:
                pass


@pytest.mark.slow
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


@pytest.mark.slow
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
                "game_id": "mock-game",
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
