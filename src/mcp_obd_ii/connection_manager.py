"""
OBD connection lifecycle management.

Provides singleton connection manager for maintaining persistent OBD-II connections.
"""

import logging
import os
from typing import Optional, Dict, Any, List
from threading import Lock

try:
    import obd
    from obd import OBDStatus
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False
    obd = None
    OBDStatus = None

from .response_models import ConnectionState, ConnectionConfig


logger = logging.getLogger(__name__)


class MockOBDConnection:
    """Mock OBD connection for testing without hardware."""

    def __init__(self):
        self.status_value = "CAR_CONNECTED" if OBD_AVAILABLE else "NOT_CONNECTED"
        self.supported_commands = []
        self._mock_data = {
            "RPM": (2500.0, "revolutions_per_minute"),
            "SPEED": (65.0, "kph"),
            "COOLANT_TEMP": (90.0, "celsius"),
            "ENGINE_LOAD": (45.5, "percent"),
            "THROTTLE_POS": (25.0, "percent"),
            "INTAKE_TEMP": (35.0, "celsius"),
            "MAF": (15.2, "grams_per_second"),
            "FUEL_LEVEL": (75.0, "percent"),
        }

    def status(self):
        """Return mock status."""
        return self.status_value

    def is_connected(self):
        """Return mock connection status."""
        return True

    def query(self, command):
        """Return mock query response."""
        if not OBD_AVAILABLE:
            # Create a simple mock response
            class MockResponse:
                def __init__(self, cmd_name):
                    self.command = type('obj', (object,), {
                        'name': cmd_name,
                        'desc': f"Mock {cmd_name}"
                    })()
                    if cmd_name in MockOBDConnection()._mock_data:
                        val, unit = MockOBDConnection()._mock_data[cmd_name]
                        self.value = val
                        self.unit = unit
                    else:
                        self.value = None
                        self.unit = None
                    self.messages = []

                def is_null(self):
                    return self.value is None

            return MockResponse(getattr(command, 'name', 'UNKNOWN'))

        # Create mock response with OBD library structures
        cmd_name = command.name
        if cmd_name in self._mock_data:
            value, unit = self._mock_data[cmd_name]
            response = type('obj', (object,), {
                'value': value,
                'unit': unit,
                'command': command,
                'messages': [],
                'is_null': lambda: False
            })()
            return response
        else:
            # Return null response
            response = type('obj', (object,), {
                'value': None,
                'unit': None,
                'command': command,
                'messages': [],
                'is_null': lambda: True
            })()
            return response

    def close(self):
        """Mock close."""
        pass

    @property
    def port_name(self):
        """Return mock port name."""
        return "/dev/ttyUSB0 (mock)"

    @property
    def protocol_name(self):
        """Return mock protocol name."""
        return "ISO 15765-4 (CAN 11/500) (mock)"


class OBDConnectionManager:
    """
    Singleton OBD connection manager.

    Maintains a single persistent connection to the OBD-II adapter and vehicle.
    Provides thread-safe access to connection state and query methods.
    """

    _instance: Optional['OBDConnectionManager'] = None
    _lock: Lock = Lock()

    def __init__(self):
        """Initialize connection manager (use get_instance() instead)."""
        self._connection: Optional[Any] = None
        self._state: ConnectionState = ConnectionState.NOT_INITIALIZED
        self._config: ConnectionConfig = ConnectionConfig()
        self._error_message: Optional[str] = None
        self._mock_mode: bool = os.getenv("MOCK_OBD", "false").lower() == "true"

        if not OBD_AVAILABLE:
            logger.warning("obd library not available, enabling mock mode automatically")
            self._mock_mode = True

    @classmethod
    def get_instance(cls) -> 'OBDConnectionManager':
        """Get singleton instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def connect(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
        protocol: Optional[str] = None,
        fast: bool = True,
        timeout: float = 0.1,
        check_voltage: bool = True,
        start_low_power: bool = False
    ) -> bool:
        """
        Establish OBD connection.

        Args:
            port: Serial port (None = auto-detect)
            baudrate: Baud rate (None = auto-detect)
            protocol: OBD protocol (None = auto-detect)
            fast: Enable command optimization
            timeout: Response timeout in seconds
            check_voltage: Check adapter voltage on connect
            start_low_power: Start in low-power mode

        Returns:
            bool: True if connection successful
        """
        with self._lock:
            # Close existing connection
            if self._connection is not None:
                self.disconnect()

            self._state = ConnectionState.CONNECTING
            self._config = ConnectionConfig(
                port=port,
                baudrate=baudrate,
                protocol=protocol,
                fast=fast,
                timeout=timeout,
                check_voltage=check_voltage,
                start_low_power=start_low_power
            )

            try:
                if self._mock_mode:
                    logger.info("Creating mock OBD connection")
                    self._connection = MockOBDConnection()
                    self._state = ConnectionState.CONNECTED
                    return True

                logger.info(f"Connecting to OBD (port={port}, baudrate={baudrate}, protocol={protocol})")

                self._connection = obd.OBD(
                    portstr=port,
                    baudrate=baudrate,
                    protocol=protocol,
                    fast=fast,
                    timeout=timeout,
                    check_voltage=check_voltage,
                    start_low_power=start_low_power
                )

                # Check connection status
                if self._connection.status() == OBDStatus.CAR_CONNECTED:
                    self._state = ConnectionState.CONNECTED
                    self._error_message = None
                    logger.info(f"OBD connection established: {self._connection.port_name}")
                    return True
                else:
                    self._state = ConnectionState.ERROR
                    self._error_message = f"Connection failed with status: {self._connection.status()}"
                    logger.error(self._error_message)
                    return False

            except Exception as e:
                self._state = ConnectionState.ERROR
                self._error_message = str(e)
                logger.exception("Failed to establish OBD connection")
                return False

    def disconnect(self) -> None:
        """Close OBD connection gracefully."""
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                    logger.info("OBD connection closed")
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")
                finally:
                    self._connection = None
                    self._state = ConnectionState.DISCONNECTED

    def is_connected(self) -> bool:
        """Check if connection is active."""
        with self._lock:
            if self._connection is None:
                return False
            if self._mock_mode:
                return True
            return self._connection.is_connected()

    def get_connection(self) -> Optional[Any]:
        """Get the active OBD connection (not thread-safe, use with caution)."""
        return self._connection

    def get_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive connection status.

        Returns:
            dict: Status information including state, protocol, port, supported commands
        """
        with self._lock:
            status = {
                "state": self._state.value,
                "connected": self.is_connected(),
                "mock_mode": self._mock_mode
            }

            if self._error_message:
                status["error"] = self._error_message

            if self._connection is not None and self.is_connected():
                try:
                    status["port"] = self._connection.port_name
                    status["protocol"] = self._connection.protocol_name

                    if hasattr(self._connection, 'supported_commands'):
                        status["supported_commands_count"] = len(self._connection.supported_commands)

                    if not self._mock_mode and hasattr(self._connection, 'status'):
                        status["obd_status"] = str(self._connection.status())

                except Exception as e:
                    logger.error(f"Error getting status details: {e}")

            return status

    def get_supported_commands(self) -> List[str]:
        """
        Get list of PIDs supported by connected vehicle.

        Returns:
            list: List of supported command names
        """
        with self._lock:
            if self._connection is None or not self.is_connected():
                return []

            if self._mock_mode:
                # Return mock supported commands
                mock_conn = self._connection
                if hasattr(mock_conn, '_mock_data'):
                    return list(mock_conn._mock_data.keys())
                return []

            try:
                if hasattr(self._connection, 'supported_commands'):
                    return [cmd.name for cmd in self._connection.supported_commands]
            except Exception as e:
                logger.error(f"Error getting supported commands: {e}")

            return []

    def query_command(self, command, force: bool = False):
        """
        Query a single OBD command.

        Args:
            command: OBD command object
            force: Force query even if not reported as supported

        Returns:
            OBD response object or None
        """
        with self._lock:
            if self._connection is None or not self.is_connected():
                return None

            try:
                return self._connection.query(command, force=force)
            except Exception as e:
                logger.error(f"Error querying command {command}: {e}")
                return None
