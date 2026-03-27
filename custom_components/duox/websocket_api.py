"""WebSocket API for Fermax Duox — exposes call info to the frontend."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


async def async_register_ws_api(hass: HomeAssistant) -> None:
    """Register WebSocket commands."""
    websocket_api.async_register_command(hass, ws_get_active_call)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "duox/active_call",
        vol.Required("entry_id"): str,
    }
)
@callback
def ws_get_active_call(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the current active call data (or null if none)."""
    entry_id = msg["entry_id"]
    data = hass.data.get(DOMAIN, {}).get(entry_id)

    if not data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    active_call = data.get("active_call")
    if not active_call:
        connection.send_result(msg["id"], None)
        return

    client = data.get("client")
    oauth_token = ""
    if client and client._token_data:
        oauth_token = client._token_data.get("access_token", "")

    result = {
        **active_call,
        "oauth_token": oauth_token,
        "gcm_token": data.get("gcm_token", ""),
    }
    connection.send_result(msg["id"], result)
