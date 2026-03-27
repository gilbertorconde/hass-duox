"""The Fermax Duox integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .coordinator import FermaxCoordinator
from .fermax_api import FermaxAuthError, FermaxClient

LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fermax Duox from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.token")

    token_data = await store.async_load()

    def save_token(token: dict) -> None:
        hass.async_create_task(store.async_save(token))

    client = FermaxClient(session, token_data, save_token)

    try:
        if not client.token_valid:
            username = entry.data.get(CONF_USERNAME)
            password = entry.data.get(CONF_PASSWORD)
            if username and password:
                await client.async_login(username, password)
            else:
                LOGGER.warning("No credentials found for re-authentication")
                return False
    except FermaxAuthError as err:
        LOGGER.error("Authentication failed during setup: %s", err)
        return False

    pairings = await client.async_get_pairings()

    device_info: dict = {}
    for pairing in pairings:
        info = await client.async_get_device_info(pairing.device_id)
        device_info[pairing.device_id] = info

    coordinator = FermaxCoordinator(hass, client, pairings)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "pairings": pairings,
        "device_info": device_info,
        "coordinator": coordinator,
        "has_fcm": False,
        "notification_listener": None,
    }

    has_fcm = await _start_fcm_listener(hass, entry, client)
    hass.data[DOMAIN][entry.entry_id]["has_fcm"] = has_fcm

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def _start_fcm_listener(
    hass: HomeAssistant, entry: ConfigEntry, client: FermaxClient
) -> bool:
    """Attempt to start the FCM notification listener. Returns True if successful."""
    try:
        from .notifications import FermaxNotificationListener  # noqa: E402

        listener = FermaxNotificationListener(hass, client, entry.entry_id)
        await listener.async_start()
        hass.data[DOMAIN][entry.entry_id]["notification_listener"] = listener

        async def _stop_listener(event: object) -> None:
            await listener.async_stop()

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_listener)
        )

        LOGGER.info("FCM doorbell notification listener active")
        return True
    except ImportError:
        LOGGER.info(
            "firebase-messaging not installed; doorbell notifications disabled"
        )
        return False
    except Exception:
        LOGGER.exception("Failed to start FCM notification listener")
        return False


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    listener = hass.data[DOMAIN][entry.entry_id].get("notification_listener")
    if listener:
        await listener.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
