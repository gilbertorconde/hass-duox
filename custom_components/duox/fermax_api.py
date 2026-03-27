"""Fermax Duox API Client."""
from __future__ import annotations

import datetime
import logging
from base64 import b64decode
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import aiohttp

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://pro-duoxme.fermax.io"
AUTH_URL = "https://oauth-pro-duoxme.fermax.io/oauth/token"

CLIENT_ID_SECRET_B64 = (
    "ZHB2N2lxejZlZTVtYXptMWlxOWR3MWQ0MnNseXV0NDhrajBtcDVmd"
    "m81OGo1aWg6Yzd5bGtxcHVqd2FoODV5aG5wcnYwd2R2eXp1dGxjbm"
    "t3NHN6OTBidWxkYnVsazE="
)

COMMON_HEADERS = {
    "app-version": "3.2.1",
    "accept-language": "en-ES;q=1.0, es-ES;q=0.9",
    "phone-os": "16.4",
    "user-agent": (
        "Blue/3.2.1 (com.fermax.bluefermax; build:3; iOS 16.4.0) Alamofire/3.2.1"
    ),
    "phone-model": "iPad14,5",
    "app-build": "3",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AccessId:
    block: int
    subblock: int
    number: int

    def to_dict(self) -> dict[str, int]:
        return {"block": self.block, "subblock": self.subblock, "number": self.number}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccessId:
        return cls(
            block=data["block"],
            subblock=data["subblock"],
            number=data["number"],
        )


@dataclass
class AccessDoor:
    name: str
    title: str
    access_id: AccessId
    visible: bool

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AccessDoor:
        return cls(
            name=name,
            title=data.get("title", name),
            access_id=AccessId.from_dict(data["accessId"]),
            visible=data.get("visible", True),
        )


@dataclass
class Pairing:
    id: str
    device_id: str
    tag: str
    status: str
    master: bool
    home: str | None
    address: str | None
    access_doors: list[AccessDoor] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Pairing:
        access_doors: list[AccessDoor] = []
        for door_name, door_data in data.get("accessDoorMap", {}).items():
            access_doors.append(AccessDoor.from_dict(door_name, door_data))
        return cls(
            id=data["id"],
            device_id=data["deviceId"],
            tag=data.get("tag", ""),
            status=data.get("status", ""),
            master=data.get("master", False),
            home=data.get("home"),
            address=data.get("address"),
            access_doors=access_doors,
        )


@dataclass
class DeviceInfo:
    device_id: str
    connection_state: str
    status: str
    family: str
    type: str
    subtype: str
    connectable: bool
    wireless_signal: int
    photocaller: bool
    divert_service: str
    blue_stream: bool
    streaming_mode: str
    installation_id: str = ""
    num_block: int = 0
    num_subblock: int = 0
    unit_number: int = 0

    @property
    def is_connected(self) -> bool:
        return self.connection_state == "Connected"

    @property
    def model(self) -> str:
        parts = [self.type, self.subtype, self.family]
        model = " ".join(p for p in parts if p).strip()
        return model or "Fermax Duox Device"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceInfo:
        return cls(
            device_id=data.get("deviceId", ""),
            connection_state=data.get("connectionState", ""),
            status=data.get("status", ""),
            family=data.get("family", ""),
            type=data.get("type", ""),
            subtype=data.get("subtype", ""),
            connectable=data.get("connectable", False),
            wireless_signal=data.get("wirelessSignal", 0),
            photocaller=data.get("photocaller", False),
            divert_service=data.get("divertService", ""),
            blue_stream=data.get("blueStream", False),
            streaming_mode=data.get("streamingMode", ""),
            installation_id=data.get("installationId", ""),
            num_block=data.get("numBlock", 0),
            num_subblock=data.get("numSubblock", 0),
            unit_number=data.get("unitNumber", 0),
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FermaxError(HomeAssistantError):
    """Base error for Fermax."""


class FermaxAuthError(FermaxError):
    """Authentication error."""


class FermaxConnectionError(FermaxError):
    """Connection error."""


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


class FermaxClient:
    """Fermax Duox API Client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token_data: dict[str, Any] | None = None,
        save_token_callback: Callable[[dict[str, Any]], Any] | None = None,
    ):
        self._session = session
        self._token_data = token_data
        self._save_token_callback = save_token_callback

    # -- Token management ---------------------------------------------------

    @property
    def token_valid(self) -> bool:
        if not self._token_data:
            return False
        expires_at = self._token_data.get("expires_at")
        if not expires_at:
            return False
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.datetime.fromisoformat(expires_at)
            except ValueError:
                return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        return datetime.datetime.now(datetime.timezone.utc) < expires_at

    async def async_login(self, username: str, password: str) -> None:
        headers = {
            "Authorization": f"Basic {CLIENT_ID_SECRET_B64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        try:
            async with self._session.post(
                AUTH_URL, headers=headers, data=data
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    LOGGER.error("Login failed: %s - %s", resp.status, text)
                    raise FermaxAuthError(f"Login failed: {resp.status}")
                json_data = await resp.json()
                self._process_token_response(json_data)
        except aiohttp.ClientError as err:
            raise FermaxConnectionError(
                f"Connection error during login: {err}"
            ) from err

    async def async_refresh_token(self) -> None:
        if not self._token_data or "refresh_token" not in self._token_data:
            raise FermaxAuthError("No refresh token available")
        headers = {
            "Authorization": f"Basic {CLIENT_ID_SECRET_B64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._token_data["refresh_token"],
        }
        try:
            async with self._session.post(
                AUTH_URL, headers=headers, data=data
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    LOGGER.error(
                        "Token refresh failed: %s - %s", resp.status, text
                    )
                    raise FermaxAuthError(f"Token refresh failed: {resp.status}")
                json_data = await resp.json()
                self._process_token_response(json_data)
        except aiohttp.ClientError as err:
            raise FermaxConnectionError(
                f"Connection error during refresh: {err}"
            ) from err

    def _process_token_response(self, data: dict[str, Any]) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_in = data.get("expires_in", 3600)
        expires_at = now + datetime.timedelta(seconds=expires_in)
        old_refresh = (
            self._token_data.get("refresh_token") if self._token_data else None
        )
        self._token_data = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", old_refresh),
            "expires_at": expires_at.isoformat(),
            "token_type": data.get("token_type", "Bearer"),
        }
        if self._save_token_callback:
            self._save_token_callback(self._token_data)

    # -- Authenticated requests ---------------------------------------------

    async def _async_request(self, method: str, url: str, **kwargs: Any) -> Any:
        if not self.token_valid:
            try:
                await self.async_refresh_token()
            except FermaxAuthError as err:
                raise ConfigEntryAuthFailed(
                    "Token expired and refresh failed"
                ) from err

        headers = kwargs.pop("headers", {})
        headers.update(COMMON_HEADERS)
        headers["Authorization"] = f"Bearer {self._token_data['access_token']}"
        headers["Content-Type"] = "application/json"

        try:
            async with self._session.request(
                method, url, headers=headers, **kwargs
            ) as resp:
                if resp.status == 401:
                    LOGGER.info("Received 401, trying to refresh token")
                    try:
                        await self.async_refresh_token()
                    except FermaxAuthError as err:
                        raise ConfigEntryAuthFailed(
                            f"Re-authentication required: {err}"
                        ) from err
                    headers["Authorization"] = (
                        f"Bearer {self._token_data['access_token']}"
                    )
                    async with self._session.request(
                        method, url, headers=headers, **kwargs
                    ) as resp2:
                        if resp2.status == 401:
                            raise ConfigEntryAuthFailed(
                                "Authentication failed after refresh"
                            )
                        resp2.raise_for_status()
                        return await self._parse_response(resp2)

                resp.raise_for_status()
                return await self._parse_response(resp)

        except aiohttp.ClientError as err:
            raise FermaxConnectionError(f"Request error: {err}") from err

    @staticmethod
    async def _parse_response(resp: aiohttp.ClientResponse) -> Any:
        ct = resp.headers.get("Content-Type", "")
        if ct.startswith("application/json"):
            return await resp.json()
        return await resp.text()

    # -- Public API methods -------------------------------------------------

    async def async_get_pairings(self) -> list[Pairing]:
        url = f"{BASE_URL}/pairing/api/v3/pairings/me"
        raw = await self._async_request("GET", url)
        return [Pairing.from_dict(p) for p in raw]

    async def async_get_pairings_raw(self) -> list[dict[str, Any]]:
        url = f"{BASE_URL}/pairing/api/v3/pairings/me"
        return await self._async_request("GET", url)

    async def async_get_device_info(self, device_id: str) -> DeviceInfo:
        url = f"{BASE_URL}/deviceaction/api/v1/device/{device_id}"
        raw = await self._async_request("GET", url)
        return DeviceInfo.from_dict(raw)

    async def async_open_door(
        self, device_id: str, access_id: AccessId
    ) -> None:
        url = f"{BASE_URL}/deviceaction/api/v1/device/{device_id}/directed-opendoor"
        await self._async_request("POST", url, json=access_id.to_dict())

    async def async_f1(self, device_id: str) -> None:
        url = f"{BASE_URL}/deviceaction/api/v1/device/{device_id}/f1"
        await self._async_request("POST", url, json={"deviceID": device_id})

    async def async_register_app_token(
        self, token: str, active: bool = True
    ) -> None:
        """Register/unregister FCM token with Fermax for push notifications."""
        url = f"{BASE_URL}/notification/api/v1/apptoken"
        await self._async_request(
            "POST",
            url,
            json={
                "token": token,
                "appVersion": "3.3.2",
                "locale": "en",
                "os": "Android",
                "osVersion": "Android 13",
                "active": active,
            },
        )

    async def async_acknowledge_notification(self, fcm_message_id: str) -> None:
        """Acknowledge a call notification."""
        url = f"{BASE_URL}/callmanager/api/v1/message/ack"
        await self._async_request(
            "POST",
            url,
            json={"attended": True, "fcmMessageId": fcm_message_id},
        )

    async def async_get_call_registry(
        self, app_token: str
    ) -> list[dict[str, Any]]:
        """Fetch call registry entries for the registered FCM token."""
        url = (
            f"{BASE_URL}/callManager/api/v1/callregistry/participant"
            f"?appToken={app_token}&callRegistryType=all"
        )
        result = await self._async_request("GET", url)
        if isinstance(result, list):
            return result
        return []

    async def async_get_photo(self, photo_id: str) -> bytes | None:
        """Fetch a doorbell snapshot by photo ID. Returns decoded image bytes."""
        url = f"{BASE_URL}/callManager/api/v1/photocall?photoId={photo_id}"
        result = await self._async_request("GET", url)
        if not isinstance(result, dict):
            return None
        image_data = (result.get("image") or {}).get("data")
        if not image_data:
            return None
        try:
            return b64decode(image_data)
        except Exception:
            LOGGER.warning("Failed to decode photo data for %s", photo_id)
            return None

    async def async_autoon(
        self, device_id: str, directed_to: str
    ) -> None:
        """Initiate an outbound monitor call to the panel camera.

        This triggers the Fermax panel to start a video session and send
        an FCM notification with streaming metadata (RoomId, SocketUrl, etc.).
        """
        url = (
            f"{BASE_URL}/deviceaction/api/v1/device/{device_id}/autoon"
            f"?deviceID={device_id}&directedTo={directed_to}"
        )
        await self._async_request(
            "POST",
            url,
            json={"directedTo": directed_to, "deviceID": device_id},
        )
