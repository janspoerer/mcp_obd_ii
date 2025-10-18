"""
Response data structures for MCP OBD-II server.

Provides standardized response envelopes and data models for OBD-II operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, List, Dict
from enum import Enum


class ConnectionState(Enum):
    """OBD connection states."""
    NOT_INITIALIZED = "NOT_INITIALIZED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class OBDErrorType(Enum):
    """OBD error categories."""
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    DEVICE_DISCONNECTED = "DEVICE_DISCONNECTED"
    UNSUPPORTED_COMMAND = "UNSUPPORTED_COMMAND"
    TIMEOUT = "TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DECODER_ERROR = "DECODER_ERROR"
    SERIAL_ERROR = "SERIAL_ERROR"
    CUSTOM_COMMAND_ERROR = "CUSTOM_COMMAND_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class ErrorInfo:
    """Error information."""
    type: str
    message: str
    suggestion: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass
class Metadata:
    """Response metadata."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    execution_time_ms: Optional[float] = None
    vehicle_connected: Optional[bool] = None
    protocol: Optional[str] = None
    port: Optional[str] = None


@dataclass
class OBDResponse:
    """Standard OBD-II response envelope."""
    ok: bool
    data: Optional[Dict[str, Any]] = None
    metadata: Metadata = field(default_factory=Metadata)
    errors: List[ErrorInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "ok": self.ok,
            "metadata": {
                "timestamp": self.metadata.timestamp,
            }
        }

        if self.metadata.execution_time_ms is not None:
            result["metadata"]["execution_time_ms"] = self.metadata.execution_time_ms
        if self.metadata.vehicle_connected is not None:
            result["metadata"]["vehicle_connected"] = self.metadata.vehicle_connected
        if self.metadata.protocol:
            result["metadata"]["protocol"] = self.metadata.protocol
        if self.metadata.port:
            result["metadata"]["port"] = self.metadata.port

        if self.data is not None:
            result["data"] = self.data

        if self.errors:
            result["errors"] = [
                {
                    "type": e.type,
                    "message": e.message,
                    **({"suggestion": e.suggestion} if e.suggestion else {}),
                    **({"context": e.context} if e.context else {})
                }
                for e in self.errors
            ]

        if self.warnings:
            result["warnings"] = self.warnings

        return result


@dataclass
class PIDData:
    """Individual PID query result."""
    pid: str
    description: str
    value: Any
    unit: Optional[str] = None
    raw_value: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "pid": self.pid,
            "description": self.description,
            "value": self.value,
            "timestamp": self.timestamp
        }
        if self.unit:
            result["unit"] = self.unit
        if self.raw_value:
            result["raw_value"] = self.raw_value
        return result


@dataclass
class ConnectionConfig:
    """OBD connection configuration."""
    port: Optional[str] = None
    baudrate: Optional[int] = None
    protocol: Optional[str] = None
    fast: bool = True
    timeout: float = 0.1
    check_voltage: bool = True
    start_low_power: bool = False


# PID category mappings
PID_CATEGORIES = {
    "engine": [
        "ENGINE_LOAD", "COOLANT_TEMP", "RPM", "SPEED", "TIMING_ADVANCE",
        "INTAKE_TEMP", "THROTTLE_POS", "RUN_TIME", "INTAKE_PRESSURE",
        "MAF", "THROTTLE_ACTUATOR", "RUN_TIME_MIL", "FUEL_INJECT_TIMING",
        "ENGINE_FUEL_RATE"
    ],
    "fuel": [
        "FUEL_STATUS", "SHORT_FUEL_TRIM_1", "LONG_FUEL_TRIM_1",
        "SHORT_FUEL_TRIM_2", "LONG_FUEL_TRIM_2", "FUEL_PRESSURE",
        "FUEL_RAIL_PRESSURE_VAC", "FUEL_RAIL_PRESSURE_DIRECT",
        "FUEL_LEVEL", "ETHANOL_PERCENT", "FUEL_TYPE"
    ],
    "emissions": [
        "O2_B1S1", "O2_B1S2", "O2_B2S1", "O2_B2S2",
        "O2_S1_WR_VOLTAGE", "O2_S2_WR_VOLTAGE", "O2_S3_WR_VOLTAGE",
        "O2_S4_WR_VOLTAGE", "O2_S5_WR_VOLTAGE", "O2_S6_WR_VOLTAGE",
        "O2_S7_WR_VOLTAGE", "O2_S8_WR_VOLTAGE",
        "CATALYST_TEMP_B1S1", "CATALYST_TEMP_B2S1",
        "CATALYST_TEMP_B1S2", "CATALYST_TEMP_B2S2",
        "EGR", "EGR_ERROR", "EVAP_VAPOR_PRESSURE", "EVAP_VAPOR_PRESSURE_ALT",
        "EVAP_VAPOR_PRESSURE_ABS"
    ],
    "status": [
        "STATUS", "STATUS_DRIVE_CYCLE", "DTC_STATUS", "PIDS_A", "PIDS_B",
        "PIDS_C", "OBD_COMPLIANCE", "MONITOR_O2_B1S1", "MONITOR_O2_B1S2",
        "MONITOR_O2_B2S1", "MONITOR_O2_B2S2"
    ],
    "distance": [
        "DISTANCE_W_MIL", "DISTANCE_SINCE_DTC_CLEAR", "WARMUPS_SINCE_DTC_CLEAR",
        "TIME_SINCE_DTC_CLEAR", "TIME_WITH_MIL"
    ],
    "air": [
        "AIR_STATUS", "COMMANDED_EQUIV_RATIO", "RELATIVE_THROTTLE_POS",
        "AMBIANT_AIR_TEMP", "THROTTLE_POS_B", "THROTTLE_POS_C",
        "ACCELERATOR_POS_D", "ACCELERATOR_POS_E", "ACCELERATOR_POS_F",
        "COMMANDED_THROTTLE_ACTUATOR", "ABSOLUTE_LOAD"
    ],
    "diagnostics": [
        "FREEZE_DTC", "GET_DTC", "CLEAR_DTC"
    ]
}
