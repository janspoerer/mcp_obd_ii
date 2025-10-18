"""
MCP OBD-II Server - Vehicle Diagnostics via Model Context Protocol

FastMCP server for OBD-II vehicle diagnostics. Provides read/write access to
vehicle diagnostic systems including sensor data, trouble codes, and readiness
monitors.

⚠️ SAFETY & LEGAL WARNINGS ⚠️

SAFE OPERATIONS (Read-Only):
All PID queries, status checks, and diagnostic reads are completely safe and
cannot harm the vehicle.

OPERATIONS REQUIRING CAUTION:

Clearing DTCs (Diagnostic Trouble Codes):
- Permanently erases diagnostic history and freeze frame data
- Resets readiness monitors (vehicle will fail emission testing)
- Does NOT fix underlying problems
- Can hide issues leading to expensive damage ($1,000-8,000+)
- May constitute fraud if used to pass emission testing
- May void manufacturer warranty

BEST PRACTICES - DO:
✓ Read and save DTCs before clearing
✓ Save freeze frame data for records
✓ Fix problems before clearing codes
✓ Use for legitimate diagnostics and repairs
✓ Keep vehicle stationary during diagnostics
✓ Ensure adequate ventilation

BEST PRACTICES - DON'T:
✗ Clear codes to hide problems (fraud)
✗ Use while driving (distraction/safety risk)
✗ Attempt to modify ECU settings
✗ Use write modes in custom PIDs
✗ Tamper with emission systems
✗ Violate applicable laws

LEGAL NOTICES:

Emission Tampering (US Federal Crime):
- Clearing codes to pass testing fraudulently: Up to $3,750/violation
- Defeating emission monitors or controls: Federal offense
- Providing tools that automate tampering: Legal liability

Odometer Fraud (Federal Crime):
- Modifying stored mileage: Up to 3 years imprisonment + $10,000 fine

Warranty:
- Improper diagnostic tool use may void manufacturer warranty

This tool does NOT enable and explicitly blocks:
✗ ECU reprogramming/flashing
✗ VIN modification
✗ Odometer changes
✗ Emission system defeats
✗ Security system bypasses

DISCLAIMER:
This software is provided "AS IS" without warranty. Users assume all
responsibility for safe operation, compliance with laws, and any damage
resulting from use. This is NOT a substitute for professional diagnostic
equipment or qualified mechanic expertise.

When in doubt, consult a qualified mechanic or vehicle manufacturer documentation.
"""

import logging
from typing import Optional, List
from difflib import get_close_matches
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
from mcp_obd_ii import dtc_tools


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
        error_msg = status.get('error', 'Connection failed')

        # Analyze error and provide specific suggestions
        suggestions = []

        if "permission denied" in error_msg.lower():
            suggestions.append("Permission denied. Add your user to the 'dialout' group: sudo usermod -a -G dialout $USER (then logout/login)")
            suggestions.append("Or run with sudo (not recommended for production)")
        elif "no such file" in error_msg.lower() or "device not found" in error_msg.lower():
            suggestions.append("Device not found. Check available ports: ls /dev/tty* | grep -E '(USB|ACM|rfcomm)'")
            suggestions.append("For Bluetooth: Ensure adapter is paired AND connected (not just paired)")
            suggestions.append("Try specifying port manually: obd_connect(port='/dev/ttyUSB0')")
        elif "timeout" in error_msg.lower():
            suggestions.append("Connection timeout. Increase timeout: obd_connect(timeout=1.0)")
            suggestions.append("Check vehicle ignition is ON (not just ACC)")
            suggestions.append("Try different baud rate: obd_connect(baudrate=38400) or baudrate=115200")
        else:
            suggestions.append("Check that OBD adapter is connected and vehicle ignition is on")
            suggestions.append("Try manual port specification: obd_connect(port='/dev/ttyUSB0')")

        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.CONNECTION_FAILED.value,
                message=error_msg,
                suggestion=" | ".join(suggestions)
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

    # Log that disconnect is happening (might block on ongoing queries)
    logger.info("Disconnecting from OBD... (waiting for ongoing queries to complete)")

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

    # Verify connection is actually alive with a lightweight query
    connection = manager.get_connection()
    actual_connected = False

    if manager.is_connected() and connection:
        try:
            # Query STATUS to verify connection is alive
            # This is lightweight and works on all vehicles
            if OBD_AVAILABLE and hasattr(obd, 'commands') and hasattr(obd.commands, 'STATUS'):
                test_response = connection.query(obd.commands.STATUS)
                actual_connected = not test_response.is_null()
            else:
                # In mock mode or without obd library, trust manager
                actual_connected = True
        except Exception as e:
            logger.warning(f"Connection appears stale: {e}")
            actual_connected = False

    status = helpers.format_status_response(connection)
    status['connected'] = actual_connected  # Override with actual status

    # Get vehicle metadata if actually connected
    vehicle_meta = {}
    if actual_connected and connection:
        vehicle_meta = helpers.get_vehicle_metadata(connection)

    return OBDResponse(
        ok=True,
        data={**status, **vehicle_meta},
        metadata=Metadata(
            vehicle_connected=actual_connected,
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
        # Get supported commands for fuzzy matching
        supported = manager.get_supported_commands()

        # Find close matches (potential typos)
        close_matches = get_close_matches(pid_name, supported, n=3, cutoff=0.6)

        suggestion = "Use obd_list_supported() to see available PIDs"
        if close_matches:
            suggestion = f"Did you mean: {', '.join(close_matches)}? Or use obd_list_supported() to see all PIDs"

        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                message=f"PID '{pid_name}' not supported or query failed",
                suggestion=suggestion
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
    categorized_pids = set()

    for category in helpers.get_all_categories():
        category_pids = helpers.get_pids_by_category(category)
        supported_in_category = [pid for pid in category_pids if pid in supported]
        if supported_in_category:
            categorized[category] = supported_in_category
            categorized_pids.update(supported_in_category)

    # Find uncategorized PIDs
    uncategorized = [pid for pid in supported if pid not in categorized_pids]
    if uncategorized:
        categorized["uncategorized"] = sorted(uncategorized)

    status = manager.get_status()
    return OBDResponse(
        ok=True,
        data={
            "total_count": len(supported),
            "categories": categorized,
            "all_pids": supported,
            "uncategorized_count": len(uncategorized)
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
                "description": "System Too Lean (Bank 1)"
              },
              {
                "code": "P0300",
                "description": "Random/Multiple Cylinder Misfire Detected"
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
    result = dtc_tools.get_dtcs(connection, manager)

    # Store DTCs for safety checking before clear
    if result.get('ok') and result.get('data'):
        dtcs = result['data'].get('dtcs', [])
        manager.set_last_dtcs_read(dtcs)

    return result


@mcp.tool()
@tool_envelope
@connection_required
@log_execution
async def obd_clear_dtcs(confirm: bool = False) -> dict:
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

    Args:
        confirm: Set to True to bypass safety check and clear without reading DTCs first.
                 Not recommended - always read DTCs before clearing!

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

    # Safety check: Require user to read DTCs before clearing
    last_dtcs = manager.get_last_dtcs_read()
    if last_dtcs is None and not confirm:
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type="CONFIRMATION_REQUIRED",
                message="Safety check failed: DTCs have not been read yet.",
                suggestion="Call obd_get_dtcs() first to see what codes you're clearing. Or pass confirm=True to bypass this safety check (NOT RECOMMENDED)."
            )]
        ).to_dict()

    result = dtc_tools.clear_dtcs(connection, manager)

    # Clear stored DTCs after successful clear
    if result.get('ok'):
        manager.clear_last_dtcs_read()

    return result


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
    return dtc_tools.get_pending_dtcs(connection, manager)


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
    return dtc_tools.get_freeze_frame(connection, manager, dtc_code)


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
            "message": "Full monitor parsing not yet implemented",
            "raw_status": "<obd.Status object ...>"
          }
        }

    Note: Full monitor parsing is not yet implemented. Currently only returns
    MIL status and DTC count. Individual monitor status (catalyst, EVAP, O2,
    etc.) parsing will be added in a future update.

    Security:
        ✅ SAFE - Read-only operation, no risk to vehicle or data
    """
    manager = OBDConnectionManager.get_instance()
    connection = manager.get_connection()
    return dtc_tools.get_readiness(connection, manager)

#endregion


if __name__ == "__main__":
    mcp.run()
