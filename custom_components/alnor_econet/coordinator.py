"""Auth + polling for Alnor ecoNet archives API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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

_LOGGER = logging.getLogger(__name__)

# How long an optimistic (just-written) value may mask the archive value.
OPTIMISTIC_MAX_SECONDS = 20 * 60  # archive batches arrive every ~15 minutes
OPTIMISTIC_UNARCHIVED_SECONDS = 5 * 60  # registers the archive never reports


class AlnorEconetCoordinator(DataUpdateCoordinator[dict[str, float | int]]):

    def _publish_mqtt_command(self, parameter, value, installation_id, factory_number):
        import time, json, boto3
        from pycognito import Cognito
        from awscrt import io, mqtt, auth
        from awsiot import mqtt_connection_builder
        
        username = self.config_entry.data.get("username", self.config_entry.data.get("email"))
        password = self.config_entry.data.get("password")
        
        cog = Cognito("eu-central-1_que8JCEVH", "3qga0ntgrj7fblcgau24plp2h4", username=username)
        cog.authenticate(password=password)
        
        identity_client = boto3.client('cognito-identity', region_name='eu-central-1')
        id_resp = identity_client.get_id(
            IdentityPoolId='eu-central-1:d1f8d4ae-7401-4d69-b603-1e992f635253',
            Logins={'cognito-idp.eu-central-1.amazonaws.com/eu-central-1_que8JCEVH': cog.id_token}
        )
        identity_id = id_resp['IdentityId']
        
        cred_resp = identity_client.get_credentials_for_identity(
            IdentityId=identity_id,
            Logins={'cognito-idp.eu-central-1.amazonaws.com/eu-central-1_que8JCEVH': cog.id_token}
        )
        creds = cred_resp['Credentials']
        
        credentials_provider = auth.AwsCredentialsProvider.new_static(
            access_key_id=creds['AccessKeyId'],
            secret_access_key=creds['SecretKey'],
            session_token=creds['SessionToken']
        )
        
        timestamp = int(time.time() * 1000)
        client_id = f"{identity_id}-{timestamp}"
        
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
        
        mqtt_connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint="a24t7r3f2r1nrr-ats.iot.eu-central-1.amazonaws.com",
            client_bootstrap=client_bootstrap,
            region="eu-central-1",
            credentials_provider=credentials_provider,
            client_id=client_id,
            clean_session=True,
            keep_alive_secs=30
        )
        
        mqtt_connection.connect().result()
        
        topic = f"{installation_id}/{client_id}/installationRequest"
        payload = {
            "transactionId": str(timestamp)[-5:],
            "operations": [{
                "name": "PARAMS_MODIFICATION",
                "targets": [{
                    "component": factory_number,
                    "parameters": {parameter: str(value)}
                }]
            }]
        }
        
        publish_future, _ = mqtt_connection.publish(
            topic=topic, payload=json.dumps(payload), qos=mqtt.QoS.AT_LEAST_ONCE
        )
        publish_future.result()
        mqtt_connection.disconnect().result()

    async def async_set_parameter(self, parameter, value, installation_id, factory_number):
        import asyncio
        await self.hass.async_add_executor_job(
            self._publish_mqtt_command, parameter, value, installation_id, factory_number
        )


    """Polls the ecoNet archives API and exposes the latest value per register."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="alnor_econet",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self._email = entry.data[CONF_EMAIL]
        self._password = entry.data[CONF_PASSWORD]
        self.installation_id = entry.data[CONF_INSTALLATION_ID]
        self.factory_number = entry.data[CONF_FACTORY_NUMBER]
        self._cognito = None  # pycognito.Cognito, created in executor

    # --- auth (pycognito is sync -> run in executor) ---------------------
    def _authenticate(self) -> None:
        from pycognito import Cognito

        u = Cognito(
            USER_POOL_ID, CLIENT_ID, username=self._email, user_pool_region=REGION
        )
        u.authenticate(password=self._password)
        self._cognito = u

    def _valid_id_token(self) -> str:
        if self._cognito is None:
            self._authenticate()
        else:
            self._cognito.check_token()  # refreshes if expired
        return self._cognito.id_token

    async def _async_token(self) -> str:
        return await self.hass.async_add_executor_job(self._valid_id_token)

    # --- polling ---------------------------------------------------------
    async def _async_update_data(self) -> dict[str, float | int]:
        try:

            token = await self._async_token()

        except Exception as err:

            if "NotAuthorizedException" in str(err) or "Invalid Refresh Token" in str(err):

                def _force_reauth():

                    from pycognito import Cognito

                    user = self.config_entry.data.get("username", self.config_entry.data.get("email"))

                    pwd = self.config_entry.data.get("password")

                    cog = Cognito("eu-central-1_que8JCEVH", "3qga0ntgrj7fblcgau24plp2h4", username=user)

                    cog.authenticate(password=pwd)

                    return cog

                

                fresh_cog = await self.hass.async_add_executor_job(_force_reauth)

                

                # Hot-swap the dead session in memory

                if hasattr(self, "_cognito"):

                    self._cognito = fresh_cog

                elif hasattr(self, "cognito"):

                    self.cognito = fresh_cog

                    

                # Attempt to grab the token natively, or fallback to the newly minted access token

                try:

                    token = await self._async_token()

                except Exception:

                    token = fresh_cog.access_token

            else:

                raise UpdateFailed(f"Cognito auth failed: {err}") from err

        now = datetime.now(timezone.utc)
        frm = now - timedelta(minutes=LOOKBACK_MINUTES)
        body = {
            "range": [_iso(frm), _iso(now)],
            "targets": [
                {"factoryNumber": self.factory_number, "parameters": list(set(ALL_REGISTERS + ["u7074", "u7073", "u6630", "u6240", "u84"]))}
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
        latest, sample_times = _latest_values(payload)

        if not hasattr(self, "optimistic_overrides"):
            self.optimistic_overrides = {}

        # The archive is uploaded by the unit in ~15 minute batches, so a value
        # written from HA stays stale in the API for up to that long. Hold the
        # optimistic value until the archive holds a sample taken after the
        # write (or a timeout passes), instead of reverting to the stale one.
        import time
        current_time = time.time()
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
