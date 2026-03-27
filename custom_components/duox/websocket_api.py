"""WebSocket API for Fermax Duox — exposes call info to the frontend."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

LOGGER = logging.getLogger(__name__)


async def async_register_ws_api(hass: HomeAssistant) -> None:
    """Register WebSocket commands."""
    websocket_api.async_register_command(hass, ws_get_active_call)
    websocket_api.async_register_command(hass, ws_autoon)


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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "duox/autoon",
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_autoon(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Trigger an outbound monitor call, then wait for FCM to deliver call data."""
    entry_id = msg["entry_id"]
    data = hass.data.get(DOMAIN, {}).get(entry_id)

    if not data:
        connection.send_error(msg["id"], "not_found", "Integration entry not found")
        return

    client = data.get("client")
    pairings = data.get("pairings", [])
    device_info = data.get("device_info", {})

    if not pairings:
        connection.send_error(msg["id"], "no_pairing", "No pairings available")
        return

    pairing = pairings[0]
    info = device_info.get(pairing.device_id)
    if not info:
        connection.send_error(msg["id"], "no_device", "Device info not found")
        return

    LOGGER.debug(
        "autoon debug: pairing.id=%s device_id=%s installation_id=%s "
        "access_doors=%s",
        pairing.id,
        pairing.device_id,
        info.installation_id if info else "N/A",
        [(d.name, d.title, d.access_id.to_dict()) for d in pairing.access_doors],
    )

    visible_doors = [d for d in pairing.access_doors if d.visible]
    first_door = visible_doors[0] if visible_doors else pairing.access_doors[0] if pairing.access_doors else None

    LOGGER.debug(
        "autoon: device_id=%s door=%s access_id=%s",
        pairing.device_id,
        first_door.name if first_door else "none",
        first_door.access_id.to_dict() if first_door else "none",
    )

    try:
        raw_pairings = await client.async_get_pairings_raw()
        LOGGER.debug("autoon raw pairings: %s", raw_pairings)
    except Exception:
        LOGGER.debug("Could not fetch raw pairings for debug")

    try:
        data["active_call"] = None
        await client.async_autoon(
            pairing.device_id,
            first_door.access_id if first_door else None,
        )
    except Exception as err:
        LOGGER.error("autoon API call failed: %s", err)
        connection.send_error(msg["id"], "autoon_failed", str(err))
        return

    for _ in range(30):
        await asyncio.sleep(1)
        active_call = data.get("active_call")
        if active_call:
            oauth_token = ""
            if client and client._token_data:
                oauth_token = client._token_data.get("access_token", "")
            result = {
                **active_call,
                "oauth_token": oauth_token,
                "gcm_token": data.get("gcm_token", ""),
            }
            connection.send_result(msg["id"], result)
            return

    connection.send_error(
        msg["id"], "timeout", "No call data received within 30 seconds"
    )
