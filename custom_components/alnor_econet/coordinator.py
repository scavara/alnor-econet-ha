"""Data coordinator: live MQTT values with the archives API as fallback."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ALL_REGISTERS,
    ARCHIVES_API,
    CLIENT_ID,
    CONF_EMAIL,
    CONF_FACTORY_NUMBER,
    CONF_INSTALLATION_ID,
    CONF_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    LOOKBACK_MINUTES,
    REGION,
    USER_POOL_ID,
)
from .live import AlnorLiveClient, LiveError

_LOGGER = logging.getLogger(__name__)

# Registers read on every refresh: the mapped sensors plus the control registers.
READ_REGISTERS = sorted(set(ALL_REGISTERS) | {"u7074", "u7073", "u6630", "u6240", "u84"})

# How long an optimistic (just-written) value may mask a live read.
OPTIMISTIC_LIVE_SECONDS = 15
# How long an optimistic (just-written) value may mask the archive value.
OPTIMISTIC_MAX_SECONDS = 20 * 60  # archive batches arrive every ~15 minutes
OPTIMISTIC_UNARCHIVED_SECONDS = 5 * 60  # registers the archive never reports


class AlnorEconetCoordinator(DataUpdateCoordinator[dict[str, float | int]]):
    """Keeps the latest value per register.

    Values come from the live MQTT channel (current, and pushed by the unit as
    they change). The archives API, which lags by up to ~15 minutes, is only
    used as a fallback when the live channel is unavailable.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="alnor_econet",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self._email = entry.data[CONF_EMAIL]
        self._password = entry.data[CONF_PASSWORD]
        self.installation_id = entry.data[CONF_INSTALLATION_ID]
        self.factory_number = entry.data[CONF_FACTORY_NUMBER]
        self._cognito = None  # pycognito.Cognito, created in executor
        self.optimistic_overrides: dict[str, dict] = {}
        self.live_active = False
        self._live = AlnorLiveClient(
            hass.loop,
            hass.async_add_executor_job,
            self._valid_id_token,
            self.installation_id,
            self._handle_live_update,
        )

    # --- auth (pycognito is sync -> run in executor) ---------------------
    def _authenticate(self) -> None:
        from pycognito import Cognito

        u = Cognito(
            USER_POOL_ID, CLIENT_ID, username=self._email, user_pool_region=REGION
        )
        u.authenticate(password=self._password)
        self._cognito = u

    def _valid_id_token(self) -> str:
        """Return a usable ID token (blocking)."""
        if self._cognito is None:
            self._authenticate()
        else:
            try:
                self._cognito.check_token()  # refreshes if expired
            except Exception:  # noqa: BLE001 - e.g. refresh token invalidated
                self._authenticate()
        return self._cognito.id_token

    async def _async_token(self) -> str:
        return await self.hass.async_add_executor_job(self._valid_id_token)

    # --- live channel ----------------------------------------------------
    async def _async_live_values(self) -> dict | None:
        """Read all registers live; None if the live channel is unavailable."""
        for attempt in (1, 2):
            try:
                return await self._live.get_values(self.factory_number, READ_REGISTERS)
            except LiveError as err:
                if attempt == 2:
                    if self.live_active or self.data is None:
                        _LOGGER.warning(
                            "Live channel unavailable, using the delayed archive: %s", err
                        )
                    return None
        return None

    def _handle_live_update(self, component: str, values: dict) -> None:
        """The unit pushed changed values (runs in the event loop)."""
        if component != self.factory_number or self.data is None:
            return
        for key in values:
            # A pushed change is newer than anything we assumed.
            self.optimistic_overrides.pop(key, None)
        self.data.update(values)
        self.async_update_listeners()

    async def async_set_parameter(self, parameter, value, installation_id, factory_number):
        """Write a parameter to the unit."""
        try:
            result = await self._live.modify(factory_number, {parameter: str(value)})
        except LiveError as err:
            # Nothing was confirmed: drop the optimistic value and re-read.
            self.optimistic_overrides.pop(parameter, None)
            await self.async_request_refresh()
            raise HomeAssistantError(f"Could not reach the unit: {err}") from err
        if result.get("statusCode") != 0:
            _LOGGER.warning("Unit rejected %s=%s: %s", parameter, value, result)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self._live.close()

    # --- polling ---------------------------------------------------------
    async def _async_update_data(self) -> dict[str, float | int]:
        current_time = time.time()
        latest = await self._async_live_values()

        if latest is not None:
            if not self.live_active:
                _LOGGER.info("Live channel active")
            self.live_active = True
            # Live reads are current; only mask them briefly after a write so
            # a read racing the write cannot flip the entity back.
            for k, v in list(self.optimistic_overrides.items()):
                if current_time - v["timestamp"] < OPTIMISTIC_LIVE_SECONDS:
                    latest[k] = v["value"]
                else:
                    del self.optimistic_overrides[k]
            return latest

        self.live_active = False
        latest, sample_times = await self._async_archive_values()

        # The archive is uploaded by the unit in ~15 minute batches, so a value
        # written from HA stays stale in the API for up to that long. Hold the
        # optimistic value until the archive holds a sample taken after the
        # write (or a timeout passes), instead of reverting to the stale one.
        for k, v in list(self.optimistic_overrides.items()):
            age = current_time - v["timestamp"]
            sample_time = sample_times.get(k)
            if sample_time is None:
                # Register is not archived at all: nothing will ever confirm it.
                expired = age >= OPTIMISTIC_UNARCHIVED_SECONDS
            else:
                expired = sample_time > v["timestamp"] or age >= OPTIMISTIC_MAX_SECONDS
            if expired:
                del self.optimistic_overrides[k]
            else:
                latest[k] = v["value"]
        return latest

    async def _async_archive_values(self) -> tuple[dict, dict]:
        try:
            token = await self._async_token()
        except Exception as err:
            if "NotAuthorizedException" in f"{type(err).__name__} {err}":
                # Wrong/changed password: ask the user to sign in again.
                raise ConfigEntryAuthFailed("Alnor account rejected the password") from err
            raise UpdateFailed(f"Cognito auth failed: {err}") from err

        now = datetime.now(timezone.utc)
        frm = now - timedelta(minutes=LOOKBACK_MINUTES)
        body = {
            "range": [_iso(frm), _iso(now)],
            "targets": [
                {"factoryNumber": self.factory_number, "parameters": READ_REGISTERS}
            ],
            "rawData": False,
        }
        url = f"{ARCHIVES_API}/v2/registereddata/values/{self.installation_id}"
        session = async_get_clientsession(self.hass)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with session.post(url, headers=headers, json=body) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise UpdateFailed(f"API {resp.status}: {text[:200]}")
                payload = await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Request error: {err}") from err
        return _latest_values(payload)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _latest_values(payload: dict) -> tuple[dict[str, float | int], dict[str, float]]:
    """Reduce the time-series response to the most recent value per register.

    Returns (values, sample_times) where sample_times holds the epoch seconds
    of each returned value.
    """
    result: dict[str, float | int] = {}
    sample_times: dict[str, float] = {}
    for comp in payload.get("components", []):
        for param in comp.get("parameters", []):
            values = param.get("values") or []
            if values:
                result[param["key"]] = values[-1]
                timestamps = param.get("timestamps") or []
                if len(timestamps) == len(values):
                    sample_times[param["key"]] = timestamps[-1]
    return result, sample_times
