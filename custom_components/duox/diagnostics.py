"""Diagnostics support for Fermax Duox."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "access_token",
    "refresh_token",
    "gcm_token",
    "fermax_token",
    "token",
    "client_secret",
    "socket_url",
    "address",
    "installation_id",
    "installationId",
    "home",
}


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    listener = data.get("notification_listener")

    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "has_fcm": data.get("has_fcm", False),
        "listener_running": bool(listener and listener.is_running),
        "active_call": _serialize(data.get("active_call")),
        "pairings": _serialize(data.get("pairings", [])),
        "coordinator_data": _serialize(
            coordinator.data if coordinator else None
        ),
    }

    return async_redact_data(diagnostics, TO_REDACT)
