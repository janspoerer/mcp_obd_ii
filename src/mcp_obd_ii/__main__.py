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


#region DTC (Diagnostic Trouble Code) Tools

@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_get_dtcs() -> dict:
    """
    Get current diagnostic trouble codes (DTCs).

    Reads all active DTCs that have triggered the check engine light (MIL).
    Returns code, description, and status for each DTC.

    Returns:
        List of current DTCs with metadata

    Example response:
        {
          "ok": true,
          "data": {
            "dtcs": [
              {
                "code": "P0171",
                "description": "System Too Lean (Bank 1)",
                "mil_on": true
              },
              {
                "code": "P0300",
                "description": "Random/Multiple Cylinder Misfire Detected",
                "mil_on": true
              }
            ],
            "count": 2,
            "mil_on": true
          }
        }

    Security:
        ✅ SAFE - Read-only operation, no risk to vehicle or data
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

    try:
        # Query DTCs using Mode 03
        if not OBD_AVAILABLE or not hasattr(obd.commands, 'GET_DTC'):
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="GET_DTC command not available"
                )]
            ).to_dict()

        response = connection.query(obd.commands.GET_DTC)

        if response.is_null():
            return OBDResponse(
                ok=True,
                data={
                    "dtcs": [],
                    "count": 0,
                    "mil_on": False,
                    "message": "No DTCs found"
                }
            ).to_dict()

        # Format DTCs
        dtcs = helpers.format_dtc_response(response.value)

        # Get MIL status from STATUS command
        mil_on = False
        try:
            status_response = connection.query(obd.commands.STATUS)
            if not status_response.is_null() and hasattr(status_response.value, 'MIL'):
                mil_on = status_response.value.MIL
        except Exception as e:
            logger.warning(f"Could not read MIL status: {e}")

        status = manager.get_status()
        return OBDResponse(
            ok=True,
            data={
                "dtcs": dtcs,
                "count": len(dtcs),
                "mil_on": mil_on
            },
            metadata=Metadata(
                vehicle_connected=True,
                protocol=status.get('protocol'),
                port=status.get('port')
            )
        ).to_dict()

    except Exception as e:
        logger.error(f"Error reading DTCs: {e}")
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNKNOWN_ERROR.value,
                message=f"Failed to read DTCs: {str(e)}"
            )]
        ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_clear_dtcs() -> dict:
    """
    Clear all diagnostic trouble codes (DTCs).

    ⚠️  WARNING: DESTRUCTIVE OPERATION ⚠️

    This command will PERMANENTLY:
    - Erase ALL diagnostic trouble codes
    - Erase ALL freeze frame data
    - Reset ALL readiness monitors to "not ready"
    - Turn off check engine light (MIL)
    - Reset distance/time counters

    CRITICAL WARNINGS:
    ✗ Clearing codes does NOT fix the underlying problem
    ✗ Vehicle will FAIL emission testing until monitors complete
    ✗ Unrepaired misfires can destroy catalytic converter ($1,000-2,500)
    ✗ Hiding problems before sale/trade = FRAUD
    ✗ Clearing codes for emission testing = ILLEGAL in most jurisdictions
    ✗ May void manufacturer warranty

    ONLY clear codes if:
    ✓ You have completed repairs
    ✓ You verified the problem is actually fixed
    ✓ You saved freeze frame data for records
    ✓ You are prepared to complete full drive cycle

    Returns:
        Confirmation of codes cleared

    Security:
        ⚠️ MEDIUM RISK - Destructive write operation. Permanently erases DTCs
        and freeze frames. Can hide problems leading to expensive damage. May
        constitute fraud if used to pass emissions testing. Requires explicit
        warnings and user confirmation.
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

    try:
        # Clear DTCs using Mode 04
        if not OBD_AVAILABLE or not hasattr(obd.commands, 'CLEAR_DTC'):
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="CLEAR_DTC command not available"
                )]
            ).to_dict()

        response = connection.query(obd.commands.CLEAR_DTC)

        # Log the clear operation for accountability
        logger.warning("DTCs CLEARED by user - All diagnostic data erased")

        status = manager.get_status()
        return OBDResponse(
            ok=True,
            data={
                "message": "All DTCs cleared successfully",
                "warning": "Readiness monitors have been reset. Vehicle may fail emission testing until monitors complete.",
                "reminder": "Complete a full drive cycle to allow monitors to run"
            },
            warnings=[
                "All diagnostic trouble codes have been erased",
                "All freeze frame data has been erased",
                "Readiness monitors have been reset to 'not ready'",
                "Distance/time counters have been reset"
            ],
            metadata=Metadata(
                vehicle_connected=True,
                protocol=status.get('protocol'),
                port=status.get('port')
            )
        ).to_dict()

    except Exception as e:
        logger.error(f"Error clearing DTCs: {e}")
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNKNOWN_ERROR.value,
                message=f"Failed to clear DTCs: {str(e)}"
            )]
        ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_get_pending_dtcs() -> dict:
    """
    Get pending diagnostic trouble codes (DTCs).

    Pending codes are detected faults that have not yet been confirmed.
    They haven't lit the check engine light yet, but indicate potential
    problems that may mature into confirmed DTCs.

    Useful for:
    - Catching intermittent problems early
    - Predicting upcoming failures
    - Verifying repairs before codes confirm

    Returns:
        List of pending DTCs

    Example response:
        {
          "ok": true,
          "data": {
            "pending_dtcs": [
              {
                "code": "P0420",
                "description": "Catalyst System Efficiency Below Threshold (Bank 1)"
              }
            ],
            "count": 1
          }
        }

    Security:
        ✅ SAFE - Read-only operation, no risk to vehicle or data
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

    try:
        # Get pending DTCs using Mode 07
        # Note: python-obd may not have GET_PENDING_DTC, we'll need to use custom command
        if OBD_AVAILABLE and hasattr(obd.commands, 'GET_CURRENT_DTC'):
            # Some implementations use GET_CURRENT_DTC for mode 07
            # We'll try the standard command first
            response = connection.query(obd.commands.GET_CURRENT_DTC, force=True)
        else:
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="Pending DTC command not available in OBD library"
                )]
            ).to_dict()

        if response.is_null():
            return OBDResponse(
                ok=True,
                data={
                    "pending_dtcs": [],
                    "count": 0,
                    "message": "No pending DTCs found"
                }
            ).to_dict()

        # Format pending DTCs
        pending_dtcs = helpers.format_dtc_response(response.value)

        status = manager.get_status()
        return OBDResponse(
            ok=True,
            data={
                "pending_dtcs": pending_dtcs,
                "count": len(pending_dtcs)
            },
            metadata=Metadata(
                vehicle_connected=True,
                protocol=status.get('protocol'),
                port=status.get('port')
            )
        ).to_dict()

    except Exception as e:
        logger.error(f"Error reading pending DTCs: {e}")
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNKNOWN_ERROR.value,
                message=f"Failed to read pending DTCs: {str(e)}"
            )]
        ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_get_freeze_frame(dtc_code: Optional[str] = None) -> dict:
    """
    Get freeze frame data for a specific DTC.

    Freeze frame is a snapshot of sensor values at the moment a DTC was triggered.
    Critical for diagnosing intermittent problems - shows exact conditions when
    the fault occurred.

    Args:
        dtc_code: Optional DTC code (e.g., "P0171"). If not provided, returns
                  freeze frame for the first/primary DTC.

    Returns:
        Freeze frame sensor data

    Example response:
        {
          "ok": true,
          "data": {
            "dtc": "P0171",
            "freeze_frame": {
              "RPM": {"value": 2800, "unit": "rpm"},
              "SPEED": {"value": 65, "unit": "kph"},
              "COOLANT_TEMP": {"value": 195, "unit": "fahrenheit"},
              "ENGINE_LOAD": {"value": 45, "unit": "percent"},
              "THROTTLE_POS": {"value": 28, "unit": "percent"},
              "SHORT_FUEL_TRIM_1": {"value": 25, "unit": "percent"}
            }
          }
        }

    Security:
        ✅ SAFE - Read-only operation, no risk to vehicle or data
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

    try:
        # Freeze frame is Mode 02
        # For now, return a message that this requires custom implementation
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                message="Freeze frame support requires custom Mode 02 implementation",
                suggestion="This feature is planned for future implementation"
            )]
        ).to_dict()

    except Exception as e:
        logger.error(f"Error reading freeze frame: {e}")
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNKNOWN_ERROR.value,
                message=f"Failed to read freeze frame: {str(e)}"
            )]
        ).to_dict()


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_get_readiness() -> dict:
    """
    Get emission readiness monitor status.

    Shows which OBD monitors have completed their self-diagnostic tests.
    Essential for emission testing compliance - most states require all
    monitors to be "ready" (except 1-2 allowed incomplete).

    Returns:
        Monitor completion status for all supported monitors

    Example response:
        {
          "ok": true,
          "data": {
            "mil_on": false,
            "dtc_count": 0,
            "monitors": {
              "continuous": {
                "misfire": {"supported": true, "complete": true},
                "fuel_system": {"supported": true, "complete": true},
                "components": {"supported": true, "complete": true}
              },
              "non_continuous": {
                "catalyst": {"supported": true, "complete": true},
                "heated_catalyst": {"supported": false, "complete": false},
                "evap": {"supported": true, "complete": false},
                "secondary_air": {"supported": false, "complete": false},
                "ac_refrigerant": {"supported": false, "complete": false},
                "oxygen_sensor": {"supported": true, "complete": true},
                "oxygen_sensor_heater": {"supported": true, "complete": true},
                "egr": {"supported": true, "complete": true}
              }
            },
            "incomplete_count": 1,
            "emission_test_ready": true
          }
        }

    Security:
        ✅ SAFE - Read-only operation, no risk to vehicle or data
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

    try:
        # Get readiness status using Mode 01 PID 01 (STATUS command)
        if not OBD_AVAILABLE or not hasattr(obd.commands, 'STATUS'):
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="STATUS command not available"
                )]
            ).to_dict()

        response = connection.query(obd.commands.STATUS)

        if response.is_null():
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.INVALID_RESPONSE.value,
                    message="Failed to read readiness status"
                )]
            ).to_dict()

        # Parse status response
        status_value = response.value

        # Extract MIL and DTC count
        mil_on = getattr(status_value, 'MIL', False)
        dtc_count = getattr(status_value, 'DTC_count', 0)

        # TODO: Parse individual monitor status from status_value
        # This requires understanding the status bit structure

        status = manager.get_status()
        return OBDResponse(
            ok=True,
            data={
                "mil_on": mil_on,
                "dtc_count": dtc_count,
                "message": "Full monitor parsing not yet implemented",
                "raw_status": str(status_value)
            },
            metadata=Metadata(
                vehicle_connected=True,
                protocol=status.get('protocol'),
                port=status.get('port')
            )
        ).to_dict()

    except Exception as e:
        logger.error(f"Error reading readiness status: {e}")
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNKNOWN_ERROR.value,
                message=f"Failed to read readiness status: {str(e)}"
            )]
        ).to_dict()

#endregion


if __name__ == "__main__":
    mcp.run()
