"""Live MQTT channel to an Alnor ecoNet installation (AWS IoT over WebSockets).

This is the same channel the Alnor web portal uses:

* requests are published to ``<installation>/<client>/installationRequest``
  and answered on ``<installation>/<client>/installationResponse``;
* after a ``GET_VALUES`` request the unit pushes ``PARAMS_UPDATE`` messages to
  ``<installation>/installationNotifications`` for about a minute, so values
  have to be re-requested periodically to keep the pushes flowing.

The class is independent of Home Assistant so it can be exercised on its own.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

_LOGGER = logging.getLogger(__name__)

REGION = "eu-central-1"
USER_POOL_ID = "eu-central-1_que8JCEVH"
IDENTITY_POOL_ID = "eu-central-1:d1f8d4ae-7401-4d69-b603-1e992f635253"
IOT_ENDPOINT = "a24t7r3f2r1nrr-ats.iot.eu-central-1.amazonaws.com"
_LOGIN_PROVIDER = f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"

CONNECT_TIMEOUT = 20
REQUEST_TIMEOUT = 10


class LiveError(Exception):
    """The live channel could not serve a request."""


def _scalar(value: Any) -> Any:
    """Values arrive as ``[value, ...]`` lists; keep only the value."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


class AlnorLiveClient:
    """One persistent MQTT connection used for reads, pushes and writes."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        run_blocking: Callable[..., Awaitable[Any]],
        get_id_token: Callable[[], str],
        installation_id: str,
        on_update: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._loop = loop
        self._run_blocking = run_blocking
        self._get_id_token = get_id_token  # blocking
        self._installation_id = installation_id
        self._on_update = on_update

        self._conn = None
        self._healthy = False
        self._request_topic = ""
        self._response_topic = ""
        self._notification_topic = f"{installation_id}/installationNotifications"
        self._transaction_id = 0
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._conn is not None and self._healthy

    # --- connection ------------------------------------------------------
    def _blocking_connect(self):
        import boto3
        from awscrt import auth, mqtt
        from awsiot import mqtt_connection_builder

        id_token = self._get_id_token()
        identity = boto3.client("cognito-identity", region_name=REGION)
        logins = {_LOGIN_PROVIDER: id_token}
        identity_id = identity.get_id(
            IdentityPoolId=IDENTITY_POOL_ID, Logins=logins
        )["IdentityId"]
        creds = identity.get_credentials_for_identity(
            IdentityId=identity_id, Logins=logins
        )["Credentials"]

        client_id = f"{identity_id}-{int(time.time() * 1000)}"
        request_topic = f"{self._installation_id}/{client_id}/installationRequest"
        response_topic = f"{self._installation_id}/{client_id}/installationResponse"

        conn = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=IOT_ENDPOINT,
            region=REGION,
            credentials_provider=auth.AwsCredentialsProvider.new_static(
                access_key_id=creds["AccessKeyId"],
                secret_access_key=creds["SecretKey"],
                session_token=creds["SessionToken"],
            ),
            client_id=client_id,
            clean_session=True,
            keep_alive_secs=30,
            on_connection_interrupted=self._on_interrupted,
            on_connection_resumed=self._on_resumed,
        )
        conn.connect().result(timeout=CONNECT_TIMEOUT)
        try:
            for topic in (response_topic, self._notification_topic):
                future, _ = conn.subscribe(
                    topic=topic, qos=mqtt.QoS.AT_MOST_ONCE, callback=self._on_message
                )
                future.result(timeout=REQUEST_TIMEOUT)
        except Exception:
            self._blocking_disconnect(conn)
            raise
        return conn, request_topic, response_topic

    @staticmethod
    def _blocking_disconnect(conn) -> None:
        try:
            conn.disconnect().result(timeout=REQUEST_TIMEOUT)
        except Exception:  # noqa: BLE001 - best effort
            pass

    async def _ensure_connected(self) -> None:
        async with self._lock:
            if self.connected:
                return
            await self._drop()
            try:
                conn, request_topic, response_topic = await self._run_blocking(
                    self._blocking_connect
                )
            except Exception as err:
                raise LiveError(f"connect failed: {err!r}") from err
            self._conn = conn
            self._request_topic = request_topic
            self._response_topic = response_topic
            self._healthy = True
            _LOGGER.debug("Live MQTT channel connected")

    async def _drop(self) -> None:
        """Tear the connection down; the next request reconnects from scratch.

        Reconnecting from scratch (instead of letting the client auto-resume)
        also renews the temporary AWS credentials, which expire after an hour.
        """
        conn, self._conn = self._conn, None
        self._healthy = False
        for future in self._pending.values():
            if not future.done():
                future.set_exception(LiveError("connection dropped"))
        self._pending.clear()
        if conn is not None:
            await self._run_blocking(self._blocking_disconnect, conn)

    async def close(self) -> None:
        async with self._lock:
            await self._drop()

    # --- callbacks from the awscrt threads -------------------------------
    def _on_interrupted(self, connection=None, error=None, **kwargs) -> None:
        self._loop.call_soon_threadsafe(self._mark_unhealthy, connection)

    def _on_resumed(self, connection=None, **kwargs) -> None:
        # Subscriptions are gone after a clean-session resume; stay unhealthy
        # so the next request rebuilds the connection.
        return

    def _mark_unhealthy(self, connection) -> None:
        if connection is None or connection is self._conn:
            self._healthy = False

    def _on_message(self, topic, payload, **kwargs) -> None:
        self._loop.call_soon_threadsafe(self._handle_message, topic, bytes(payload))

    # --- message handling (event loop) -----------------------------------
    def _handle_message(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except ValueError:
            return
        if not isinstance(data, dict):
            return

        if topic == self._response_topic:
            future = self._pending.pop(str(data.get("transactionId")), None)
            if future is not None and not future.done():
                operations = data.get("operations") or [{}]
                future.set_result(operations[0])
            return

        if topic == self._notification_topic:
            for message in data.get("messages") or []:
                if message.get("messageType") != "PARAMS_UPDATE":
                    continue
                for target in message.get("targets") or []:
                    params = target.get("parameters")
                    if not isinstance(params, dict):
                        continue
                    values = {key: _scalar(val) for key, val in params.items()}
                    try:
                        self._on_update(target.get("component"), values)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception("Error handling live update")

    # --- requests --------------------------------------------------------
    async def _request(self, operation: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_connected()
        conn = self._conn
        self._transaction_id += 1
        transaction_id = str(self._transaction_id)
        future: asyncio.Future = self._loop.create_future()
        self._pending[transaction_id] = future
        payload = json.dumps(
            {"transactionId": transaction_id, "operations": [operation]}
        )

        def _publish() -> None:
            from awscrt import mqtt

            publish_future, _ = conn.publish(
                topic=self._request_topic, payload=payload, qos=mqtt.QoS.AT_LEAST_ONCE
            )
            publish_future.result(timeout=REQUEST_TIMEOUT)

        try:
            await self._run_blocking(_publish)
            return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
        except LiveError:
            raise
        except Exception as err:
            # No answer usually means a dead connection: rebuild it next time.
            self._healthy = False
            raise LiveError(f"{operation.get('name')} failed: {err!r}") from err
        finally:
            self._pending.pop(transaction_id, None)

    async def get_values(self, component: str, parameters: list[str]) -> dict[str, Any]:
        """Read current values. Also (re)starts the unit's pushed updates."""
        result = await self._request(
            {
                "name": "GET_VALUES",
                "targets": [{"component": component, "parameters": parameters}],
            }
        )
        if result.get("statusCode") != 0:
            raise LiveError(f"GET_VALUES status {result.get('statusCode')}")
        for target in result.get("targets") or []:
            if target.get("component") == component and target.get("statusCode", 0) == 0:
                params = target.get("parameters") or {}
                return {key: _scalar(val) for key, val in params.items()}
        raise LiveError("GET_VALUES returned no data for the component")

    async def modify(self, component: str, parameters: dict[str, str]) -> dict[str, Any]:
        """Write parameters; returns the unit's reply."""
        return await self._request(
            {
                "name": "PARAMS_MODIFICATION",
                "targets": [{"component": component, "parameters": parameters}],
            }
        )
