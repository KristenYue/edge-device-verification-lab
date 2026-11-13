"""Public Python API for the edge-device verification lab."""

from .client import DeviceClient, DeviceProtocolError, DeviceTimeoutError
from .control_protocol import AlarmReport, CommunicationState, ControlMode, DeviceControlHost
from .models import DeviceResponse, RequirementResult, TaskProfile, TestRunSummary
from .smart_shelf import (
    IngestResult,
    SmartShelfContractError,
    SmartShelfGateway,
    validate_command,
    validate_telemetry,
)

__all__ = [
    "AlarmReport",
    "CommunicationState",
    "ControlMode",
    "DeviceClient",
    "DeviceControlHost",
    "DeviceProtocolError",
    "DeviceResponse",
    "DeviceTimeoutError",
    "IngestResult",
    "RequirementResult",
    "SmartShelfContractError",
    "SmartShelfGateway",
    "TaskProfile",
    "TestRunSummary",
    "validate_command",
    "validate_telemetry",
]



