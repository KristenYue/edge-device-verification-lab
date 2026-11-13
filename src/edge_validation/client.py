from __future__ import annotations

import json
import socket
import uuid
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .models import DeviceResponse, TaskProfile


class DeviceClientError(RuntimeError):
    """Base error for transport and protocol failures."""


class DeviceTimeoutError(DeviceClientError):
    """Raised when the device does not answer before the configured deadline."""


class DeviceProtocolError(DeviceClientError):
    """Raised when the device returns malformed or incomplete data."""


@dataclass(frozen=True)
class RequestEnvelope:
    request_id: str
    command: str
    params: Mapping[str, Any]
    crc32: str

    def to_bytes(self) -> bytes:
        payload = {
            "request_id": self.request_id,
            "command": self.command,
            "params": dict(self.params),
            "crc32": self.crc32,
        }
        return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def checksum(request_id: str, command: str) -> str:
    value = zlib.crc32(f"{request_id}|{command}".encode()) & 0xFFFFFFFF
    return f"{value:08X}"


class DeviceClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 1.0):
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.host = host
        self.port = port
        self.timeout = timeout

    def command(
        self,
        command: str,
        params: Mapping[str, Any] | None = None,
        *,
        request_id: str | None = None,
        corrupt_crc: bool = False,
    ) -> DeviceResponse:
        if not command:
            raise ValueError("command cannot be empty")
        resolved_id = request_id or str(uuid.uuid4())
        crc = "00000000" if corrupt_crc else checksum(resolved_id, command)
        envelope = RequestEnvelope(resolved_id, command, params or {}, crc)
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(envelope.to_bytes())
                raw = self._read_line(sock)
        except TimeoutError as exc:
            raise DeviceTimeoutError(f"timeout waiting for {command}") from exc
        except OSError as exc:
            if isinstance(exc, socket.timeout):
                raise DeviceTimeoutError(f"timeout waiting for {command}") from exc
            raise DeviceClientError(f"transport failure for {command}: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
            return DeviceResponse.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise DeviceProtocolError(f"invalid device response: {raw!r}") from exc

    @staticmethod
    def _read_line(sock: socket.socket, limit: int = 1_048_576) -> bytes:
        data = bytearray()
        while len(data) < limit:
            chunk = sock.recv(4096)
            if not chunk:
                raise DeviceProtocolError("connection closed before newline")
            data.extend(chunk)
            if b"\n" in chunk:
                return bytes(data).split(b"\n", 1)[0]
        raise DeviceProtocolError("response exceeded size limit")

    def status(self) -> DeviceResponse:
        return self.command("status")

    def power_on(self) -> DeviceResponse:
        return self.command("power_on")

    def home(self) -> DeviceResponse:
        return self.command("home")

    def calibrate(self) -> DeviceResponse:
        return self.command("calibrate")

    def load_profile(self, profile: TaskProfile) -> DeviceResponse:
        return self.command("load_profile", profile.model_dump())

    def start_run(self) -> DeviceResponse:
        return self.command("start_run")

    def inject_fault(self, fault_type: str, **params: Any) -> DeviceResponse:
        return self.command("inject_fault", {"type": fault_type, **params})


