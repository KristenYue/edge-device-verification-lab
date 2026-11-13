"""Host-side control facade for the virtual device simulator.

The facade models common device-control semantics: communication state, local/remote
ownership, remote commands, status variables, alarms, stable-ID retries and duplicate
request idempotency. It is a project-specific JSON/TCP protocol, not an industry
standard implementation.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .client import DeviceClient, DeviceClientError
from .models import DeviceResponse, TaskProfile


class CommunicationState(StrEnum):
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"


class ControlMode(StrEnum):
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"


@dataclass(frozen=True)
class AlarmReport:
    count: int
    alarms: tuple[str, ...]


class DeviceControlHost:
    """Host-side helper over the project's JSON/TCP control protocol."""

    def __init__(
        self,
        client: DeviceClient,
        *,
        max_retries: int = 1,
        retry_delay: float = 0.1,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_delay < 0:
            raise ValueError("retry_delay cannot be negative")
        self.client = client
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _send(
        self,
        command: str,
        params: Mapping[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> DeviceResponse:
        stable_request_id = request_id or str(uuid.uuid4())
        last_error: DeviceClientError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self.client.command(command, params, request_id=stable_request_id)
            except DeviceClientError as exc:
                last_error = exc
                if attempt == self.max_retries:
                    raise
                time.sleep(self.retry_delay)
        assert last_error is not None
        raise last_error

    def establish_communications(self) -> DeviceResponse:
        """Move the control channel from OFFLINE to ONLINE/LOCAL."""
        return self._send("protocol_establish_communications")

    def go_offline(self) -> DeviceResponse:
        return self._send("protocol_go_offline")

    def set_remote(self) -> DeviceResponse:
        return self._send("protocol_set_remote")

    def set_local(self) -> DeviceResponse:
        return self._send("protocol_set_local")

    def variables(self) -> dict[str, str]:
        """Return the externally observable device variables."""
        return self._send("protocol_get_variables").data

    def alarms(self) -> AlarmReport:
        """Return active device alarms."""
        response = self._send("protocol_get_alarms")
        alarms = tuple(item for item in response.data["alarms"].split(";") if item)
        return AlarmReport(count=int(response.data["alarm_count"]), alarms=alarms)

    def host_command(
        self,
        command_name: str,
        params: Mapping[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> DeviceResponse:
        """Send a command that requires ONLINE/REMOTE control."""
        payload = {"command_name": command_name, **dict(params or {})}
        return self._send("protocol_host_command", payload, request_id=request_id)

    def select_profile(
        self, profile: TaskProfile, *, request_id: str | None = None
    ) -> DeviceResponse:
        return self.host_command("PROFILE", profile.model_dump(), request_id=request_id)

    def start(self, *, request_id: str | None = None) -> DeviceResponse:
        return self.host_command("START", request_id=request_id)

    def stop(self, *, request_id: str | None = None) -> DeviceResponse:
        return self.host_command("STOP", request_id=request_id)




