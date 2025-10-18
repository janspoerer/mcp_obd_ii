"""
MCP OBD-II Server Main Entry Point

FastMCP server for OBD-II vehicle diagnostics.
"""

import logging
from typing import Optional, List
from mcp.server.fastmcp import FastMCP

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False
    obd = None

import mcp_obd_ii as MOBD
from mcp_obd_ii.decorators import tool_envelope, connection_required, log_execution
from mcp_obd_ii.connection_manager import OBDConnectionManager
from mcp_obd_ii.response_models import OBDResponse, ErrorInfo, Metadata, OBDErrorType
from mcp_obd_ii import helpers


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"mcp_obd_ii from: {getattr(MOBD, '__file__', '<namespace>')}")
logger.info(f"OBD library available: {OBD_AVAILABLE}")

# Initialize FastMCP
mcp = FastMCP("mcp_obd_ii")


#region Connection Management Tools

@mcp.tool()
@tool_envelope
@log_execution
async def obd_connect(
    port: Optional[str] = None,
    baudrate: Optional[int] = None,
    protocol: Optional[str] = None,
    fast: bool = True,
    timeout: float = 0.1,
    check_voltage: bool = True
) -> dict:
    """
    Establish connection to vehicle OBD-II port.

    Connects to the OBD-II adapter and vehicle. If port/baudrate/protocol are not
    specified, attempts auto-detection. This must be called before using other tools.

    Args:
        port: Serial port path (e.g., "/dev/ttyUSB0", "COM3"). None = auto-detect
        baudrate: Serial baud rate (e.g., 38400). None = auto-detect
        protocol: OBD protocol ID (e.g., "6" for CAN 500k). None = auto-detect
        fast: Enable command optimization for faster queries
        timeout: Response timeout in seconds
        check_voltage: Check adapter voltage on connection

    Returns:
        Connection status with vehicle info and supported commands count

    Examples:
        Auto-detect everything:
            obd_connect()

        Specify port only:
            obd_connect(port="/dev/ttyUSB0")

        Full manual configuration:
            obd_connect(port="COM3", baudrate=38400, protocol="6")

    Security:
        ✅ SAFE - Connection establishment only, no data modification
    """
    manager = OBDConnectionManager.get_instance()

    # Attempt connection
    success = manager.connect(
        port=port,
        baudrate=baudrate,
        protocol=protocol,
        fast=fast,
        timeout=timeout,
        check_voltage=check_voltage
    )

    if not success:
        status = manager.get_status()
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.CONNECTION_FAILED.value,
                message=status.get('error', 'Connection failed'),
                suggestion="Check that OBD adapter is connected and vehicle ignition is on"
            )],
            metadata=Metadata(
                vehicle_connected=False
            )
        ).to_dict()

    # Get connection status
    status = manager.get_status()

    # Get vehicle metadata if available
    connection = manager.get_connection()
    vehicle_meta = {}
    if connection:
        vehicle_meta = helpers.get_vehicle_metadata(connection)

    return OBDResponse(
        ok=True,
        data={
            "message": "OBD connection established",
            "port": status.get('port'),
            "protocol": status.get('protocol'),
            "supported_commands_count": status.get('supported_commands_count', 0),
            "mock_mode": status.get('mock_mode', False),
            **vehicle_meta
        },
        metadata=Metadata(
            vehicle_connected=True,
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()


@mcp.tool()
@tool_envelope
@log_execution
async def obd_disconnect() -> dict:
    """
    Close OBD connection gracefully.

    Disconnects from the vehicle and closes the serial port. You can reconnect
    later by calling obd_connect() again.

    Returns:
        Disconnection confirmation

    Security:
        ✅ SAFE - Connection teardown only, no data modification
    """
    manager = OBDConnectionManager.get_instance()

    if not manager.is_connected():
        return OBDResponse(
            ok=True,
            data={"message": "Already disconnected"},
            metadata=Metadata(vehicle_connected=False)
        ).to_dict()

    manager.disconnect()

    return OBDResponse(
        ok=True,
        data={"message": "OBD connection closed"},
        metadata=Metadata(vehicle_connected=False)
    ).to_dict()


@mcp.tool()
@tool_envelope
@log_execution
async def obd_status() -> dict:
    """
    Get current connection status and vehicle information.

    Returns comprehensive status including connection state, protocol info,
    supported commands count, and vehicle metadata (VIN, ECU name, etc.).

    Returns:
        Connection status, protocol, supported PIDs count, vehicle info

    Example response:
        {
          "ok": true,
          "data": {
            "state": "CONNECTED",
            "connected": true,
            "port": "/dev/ttyUSB0",
            "protocol": "ISO 15765-4 (CAN 11/500)",
            "supported_commands_count": 87,
            "supported_commands": ["RPM", "SPEED", "COOLANT_TEMP", ...],
            "vin": "1HGBH41JXMN109186",
            "ecu_name": "ECM-Engine Control"
          }
        }

    Security:
        ✅ SAFE - Read-only status query, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    status = helpers.format_status_response(manager.get_connection())

    # Get vehicle metadata if connected
    vehicle_meta = {}
    if manager.is_connected():
        connection = manager.get_connection()
        if connection:
            vehicle_meta = helpers.get_vehicle_metadata(connection)

    return OBDResponse(
        ok=True,
        data={**status, **vehicle_meta},
        metadata=Metadata(
            vehicle_connected=manager.is_connected(),
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()

#endregion


#region Basic Query Tools

@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_query_pid(
    pid_name: str,
    include_raw: bool = False
) -> dict:
    """
    Query a single PID by name.

    Reads a specific sensor value from the vehicle. The PID must be supported
    by the vehicle (check with obd_list_supported() first).

    Args:
        pid_name: PID identifier (e.g., "RPM", "SPEED", "COOLANT_TEMP")
        include_raw: Include raw hex response data for debugging

    Returns:
        PID value with unit and metadata

    Common PIDs:
        - RPM: Engine speed in revolutions per minute
        - SPEED: Vehicle speed in kph
        - COOLANT_TEMP: Engine coolant temperature in celsius
        - ENGINE_LOAD: Calculated engine load percentage
        - THROTTLE_POS: Throttle position percentage
        - FUEL_LEVEL: Fuel tank level percentage
        - INTAKE_TEMP: Intake air temperature in celsius
        - MAF: Mass air flow in grams per second

    Example response:
        {
          "ok": true,
          "data": {
            "pid": "RPM",
            "description": "Engine RPM",
            "value": 2500.0,
            "unit": "revolutions per minute",
            "timestamp": "2025-10-18T14:30:45.123Z"
          }
        }

    Security:
        ✅ SAFE - Read-only PID query, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    connection = manager.get_connection()

    if not connection:
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.NOT_CONNECTED.value,
                message="No OBD connection"
            )]
        ).to_dict()

    # Query the PID
    result = helpers.safe_query(connection, pid_name, include_raw=include_raw)

    if result is None:
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                message=f"PID '{pid_name}' not supported or query failed",
                suggestion="Use obd_list_supported() to see available PIDs"
            )]
        ).to_dict()

    status = manager.get_status()
    return OBDResponse(
        ok=True,
        data=result,
        metadata=Metadata(
            vehicle_connected=True,
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_query_multiple(
    pid_names: List[str],
    include_raw: bool = False
) -> dict:
    """
    Query multiple PIDs efficiently in one call.

    Reads multiple sensor values from the vehicle. Only supported PIDs will
    return data; unsupported PIDs are skipped silently.

    Args:
        pid_names: List of PID identifiers (e.g., ["RPM", "SPEED", "COOLANT_TEMP"])
        include_raw: Include raw hex response data

    Returns:
        Array of PID results

    Example:
        obd_query_multiple(pid_names=["RPM", "SPEED", "COOLANT_TEMP"])

    Example response:
        {
          "ok": true,
          "data": {
            "pids": [
              {"pid": "RPM", "value": 2500.0, "unit": "revolutions per minute"},
              {"pid": "SPEED", "value": 65.0, "unit": "kph"},
              {"pid": "COOLANT_TEMP", "value": 90.0, "unit": "celsius"}
            ],
            "count": 3
          }
        }

    Security:
        ✅ SAFE - Read-only batch PID query, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    connection = manager.get_connection()

    if not connection:
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.NOT_CONNECTED.value,
                message="No OBD connection"
            )]
        ).to_dict()

    # Query all PIDs
    results = helpers.batch_query(connection, pid_names, include_raw=include_raw)

    status = manager.get_status()
    return OBDResponse(
        ok=True,
        data={
            "pids": results,
            "count": len(results),
            "requested": len(pid_names),
            "success_rate": f"{len(results)}/{len(pid_names)}"
        },
        metadata=Metadata(
            vehicle_connected=True,
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_list_supported() -> dict:
    """
    List all PIDs supported by the connected vehicle.

    Returns a comprehensive list of all PIDs that the vehicle's ECU supports,
    grouped by category (engine, fuel, emissions, etc.).

    Returns:
        Supported PIDs grouped by category

    Example response:
        {
          "ok": true,
          "data": {
            "total_count": 87,
            "categories": {
              "engine": ["RPM", "SPEED", "COOLANT_TEMP", "ENGINE_LOAD", ...],
              "fuel": ["FUEL_STATUS", "FUEL_PRESSURE", "FUEL_LEVEL", ...],
              "emissions": ["O2_B1S1", "CATALYST_TEMP_B1S1", ...]
            },
            "all_pids": ["RPM", "SPEED", "COOLANT_TEMP", ...]
          }
        }

    Security:
        ✅ SAFE - Read-only command enumeration, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    supported = manager.get_supported_commands()

    # Group by category
    categorized = {}
    for category in helpers.get_all_categories():
        category_pids = helpers.get_pids_by_category(category)
        supported_in_category = [pid for pid in category_pids if pid in supported]
        if supported_in_category:
            categorized[category] = supported_in_category

    status = manager.get_status()
    return OBDResponse(
        ok=True,
        data={
            "total_count": len(supported),
            "categories": categorized,
            "all_pids": supported
        },
        metadata=Metadata(
            vehicle_connected=True,
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()

#endregion


#region Category Query Tools

@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_engine_data(include_raw: bool = False) -> dict:
    """
    Get comprehensive engine data.

    Queries all engine-related PIDs including RPM, load, temperatures,
    throttle position, timing, and more.

    Args:
        include_raw: Include raw hex response data

    Returns:
        All engine sensor values

    Typical PIDs included:
        - RPM: Engine speed
        - ENGINE_LOAD: Calculated load
        - COOLANT_TEMP: Coolant temperature
        - INTAKE_TEMP: Intake air temperature
        - TIMING_ADVANCE: Ignition timing
        - THROTTLE_POS: Throttle position
        - INTAKE_PRESSURE: Manifold pressure
        - MAF: Mass air flow
        - RUN_TIME: Time since engine start

    Security:
        ✅ SAFE - Read-only category query, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    connection = manager.get_connection()

    result = helpers.query_by_category(connection, "engine", include_raw=include_raw)

    status = manager.get_status()
    return OBDResponse(
        ok=True,
        data=result,
        metadata=Metadata(
            vehicle_connected=True,
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_fuel_system(include_raw: bool = False) -> dict:
    """
    Get fuel system data.

    Queries all fuel-related PIDs including status, pressure, level,
    fuel trim values, and fuel type.

    Args:
        include_raw: Include raw hex response data

    Returns:
        All fuel system sensor values

    Typical PIDs included:
        - FUEL_STATUS: Fuel system status
        - FUEL_PRESSURE: Fuel rail pressure
        - FUEL_LEVEL: Tank level percentage
        - SHORT_FUEL_TRIM_1/2: Short-term fuel trim
        - LONG_FUEL_TRIM_1/2: Long-term fuel trim
        - FUEL_TYPE: Fuel type (gasoline, diesel, etc.)
        - ETHANOL_PERCENT: Ethanol percentage in fuel

    Security:
        ✅ SAFE - Read-only category query, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    connection = manager.get_connection()

    result = helpers.query_by_category(connection, "fuel", include_raw=include_raw)

    status = manager.get_status()
    return OBDResponse(
        ok=True,
        data=result,
        metadata=Metadata(
            vehicle_connected=True,
            protocol=status.get('protocol'),
            port=status.get('port')
        )
    ).to_dict()

#endregion


if __name__ == "__main__":
    mcp.run()
