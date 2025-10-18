"""
DTC (Diagnostic Trouble Code) Tools

Implements check engine light functionality including:
- Reading current DTCs (confirmed codes)
- Clearing DTCs (destructive operation)
- Reading pending DTCs (not yet confirmed)
- Reading freeze frames (sensor snapshots at fault time)
- Reading readiness monitors (emission test status)
"""

import logging
from typing import Optional, Dict, Any

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False
    obd = None

from .response_models import OBDResponse, ErrorInfo, Metadata, OBDErrorType
from . import helpers


logger = logging.getLogger(__name__)


def parse_readiness_monitors(status_value) -> Dict[str, Any]:
    """
    Parse readiness monitor status from STATUS response.

    Extracts information about which OBD monitors are available and complete.
    Different monitors exist for spark vs compression ignition engines.

    Args:
        status_value: STATUS command response value object

    Returns:
        dict: Parsed monitor information with continuous/non-continuous categories
    """
    result = {
        "ignition_type": getattr(status_value, 'ignition_type', 'unknown'),
        "continuous_monitors": {},
        "non_continuous_monitors": {}
    }

    # Continuous monitors (always run on all vehicles)
    continuous_monitor_names = [
        'MISFIRE_MONITORING',
        'FUEL_SYSTEM_MONITORING',
        'COMPONENT_MONITORING'
    ]

    # Non-continuous monitors for spark ignition (gasoline)
    spark_monitor_names = [
        'CATALYST_MONITORING',
        'HEATED_CATALYST_MONITORING',
        'EVAPORATIVE_SYSTEM_MONITORING',
        'SECONDARY_AIR_SYSTEM_MONITORING',
        'AC_REFRIGERANT_MONITORING',
        'OXYGEN_SENSOR_MONITORING',
        'OXYGEN_SENSOR_HEATER_MONITORING',
        'EGR_SYSTEM_MONITORING'
    ]

    # Non-continuous monitors for compression ignition (diesel)
    compression_monitor_names = [
        'NMHC_CATALYST_MONITORING',
        'NOX_SCR_MONITORING',
        'BOOST_PRESSURE_MONITORING',
        'EXHAUST_GAS_SENSOR_MONITORING',
        'PM_FILTER_MONITORING',
        'EGR_VVT_SYSTEM_MONITORING'
    ]

    # Parse continuous monitors
    for monitor_name in continuous_monitor_names:
        if hasattr(status_value, monitor_name):
            monitor = getattr(status_value, monitor_name)
            result["continuous_monitors"][monitor_name] = {
                "available": getattr(monitor, 'available', False),
                "complete": getattr(monitor, 'complete', False)
            }

    # Parse non-continuous monitors based on ignition type
    ignition_type = result["ignition_type"]

    if ignition_type == "spark":
        monitor_list = spark_monitor_names
    elif ignition_type == "compression":
        monitor_list = compression_monitor_names
    else:
        # Unknown type - try both lists
        monitor_list = spark_monitor_names + compression_monitor_names

    for monitor_name in monitor_list:
        if hasattr(status_value, monitor_name):
            monitor = getattr(status_value, monitor_name)
            result["non_continuous_monitors"][monitor_name] = {
                "available": getattr(monitor, 'available', False),
                "complete": getattr(monitor, 'complete', False)
            }

    return result


def get_dtcs(connection, manager) -> Dict[str, Any]:
    """
    Get current diagnostic trouble codes (DTCs).

    Returns confirmed/stored DTCs that have triggered the check engine light.
    These are "two-trip" codes that have failed at least twice.

    Args:
        connection: OBD connection object
        manager: OBDConnectionManager instance

    Returns:
        dict: OBDResponse with DTCs, count, and MIL status

    Technical Details:
        Uses OBD Mode 03 (GET_DTC command).
        - Mode 03 (GET_DTC) = Confirmed/stored codes (failed twice) - THIS FUNCTION
        - Mode 07 (GET_CURRENT_DTC) = Pending codes (failed once) - See get_pending_dtcs()
    """
    try:
        # Check if OBD library is available (for non-mock mode)
        if not OBD_AVAILABLE or obd is None:
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="OBD library not available - cannot query DTCs"
                )]
            ).to_dict()

        # Query DTCs using Mode 03
        response = connection.query(obd.commands.GET_DTC)

        # Format DTCs (empty list if none found)
        dtcs = []
        if not response.is_null() and response.value:
            dtcs = helpers.format_dtc_response(response.value)

        # Get MIL status from STATUS command
        # IMPORTANT: MIL can be on even when no DTCs are stored
        # (e.g., continuous monitor failures, recent clear, etc.)
        mil_on = False
        try:
            status_response = connection.query(obd.commands.STATUS)
            if not status_response.is_null() and hasattr(status_response.value, 'MIL'):
                mil_on = status_response.value.MIL
        except Exception as e:
            logger.warning(f"Could not read MIL status: {e}")

        status = manager.get_status()

        # Build response data
        data = {
            "dtcs": dtcs,
            "count": len(dtcs),
            "mil_on": mil_on
        }

        # Add message when no DTCs found
        if len(dtcs) == 0:
            data["message"] = "No DTCs found"

        return OBDResponse(
            ok=True,
            data=data,
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


def clear_dtcs(connection, manager) -> Dict[str, Any]:
    """
    Clear all diagnostic trouble codes (DTCs).

    ⚠️ WARNING: DESTRUCTIVE OPERATION ⚠️

    Args:
        connection: OBD connection object
        manager: OBDConnectionManager instance

    Returns:
        dict: OBDResponse with confirmation and warnings
    """
    try:
        # Check if OBD library is available (for non-mock mode)
        if not OBD_AVAILABLE or obd is None:
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="OBD library not available - cannot clear DTCs"
                )]
            ).to_dict()

        # Clear DTCs using Mode 04
        response = connection.query(obd.commands.CLEAR_DTC)

        # Validate that clear command succeeded
        if response.is_null():
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.INVALID_RESPONSE.value,
                    message="Failed to clear DTCs - vehicle did not respond to clear command",
                    suggestion="Ensure ignition is on and connection is stable. Try reconnecting."
                )]
            ).to_dict()

        # Verify DTCs were actually cleared by re-querying
        verify_response = connection.query(obd.commands.GET_DTC)
        dtcs_remaining = []
        if not verify_response.is_null() and verify_response.value:
            dtcs_remaining = helpers.format_dtc_response(verify_response.value)

        # Log the clear operation for accountability - AFTER verification
        if dtcs_remaining:
            logger.warning(f"PARTIAL DTC clear - {len(dtcs_remaining)} code(s) remain after clear command")
        else:
            logger.warning("DTCs CLEARED by user - All diagnostic data erased")

        status = manager.get_status()
        result_data = {
            "message": "All DTCs cleared successfully",
            "warning": "Readiness monitors have been reset. Vehicle may fail emission testing until monitors complete.",
            "reminder": "Complete a full drive cycle to allow monitors to run"
        }

        # Build warnings list based on actual clear result
        warnings = []
        if dtcs_remaining:
            # Partial clear
            result_data["partial_clear"] = True
            result_data["remaining_dtcs"] = dtcs_remaining
            result_data["message"] = f"Clear command sent but {len(dtcs_remaining)} DTC(s) still present"
            warnings = [
                f"Clear command executed but {len(dtcs_remaining)} DTC(s) remain",
                "Some freeze frame data may still be present",
                "Readiness monitors may have been partially reset"
            ]
        else:
            # Complete clear
            warnings = [
                "All diagnostic trouble codes have been erased",
                "All freeze frame data has been erased",
                "Readiness monitors have been reset to 'not ready'",
                "Distance/time counters have been reset"
            ]

        return OBDResponse(
            ok=True,
            data=result_data,
            warnings=warnings,
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


def get_pending_dtcs(connection, manager) -> Dict[str, Any]:
    """
    Get pending diagnostic trouble codes (DTCs).

    Pending codes are detected faults that have not yet been confirmed.
    These are "one-trip" codes that have failed once but not yet twice.

    Args:
        connection: OBD connection object
        manager: OBDConnectionManager instance

    Returns:
        dict: OBDResponse with pending DTCs

    Technical Details:
        Uses OBD Mode 07 (GET_CURRENT_DTC command).
        - Mode 03 (GET_DTC) = Confirmed/hard fault codes (failed twice)
        - Mode 07 (GET_CURRENT_DTC) = Pending codes from current/last driving cycle (failed once)
        The name "CURRENT" refers to "current driving cycle", not "currently confirmed".
    """
    try:
        # Check if OBD library is available (for non-mock mode)
        if not OBD_AVAILABLE or obd is None:
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="OBD library not available - cannot query pending DTCs"
                )]
            ).to_dict()

        # Get pending DTCs using Mode 07 (GET_CURRENT_DTC)
        # VERIFIED: GET_CURRENT_DTC is Mode 07 in python-obd library
        # Returns DTCs from current/last driving cycle (one-trip failures)
        response = connection.query(obd.commands.GET_CURRENT_DTC, force=True)

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

        # Mode 07/03 confusion detection:
        # When pending DTCs found, also check confirmed DTCs to provide context
        confirmed_dtcs = []
        if pending_dtcs:
            try:
                confirmed_response = connection.query(obd.commands.GET_DTC)
                if not confirmed_response.is_null() and confirmed_response.value:
                    confirmed_dtcs = helpers.format_dtc_response(confirmed_response.value)
            except Exception as e:
                logger.warning(f"Could not query confirmed DTCs for comparison: {e}")

        # Build response data
        data = {
            "pending_dtcs": pending_dtcs,
            "count": len(pending_dtcs)
        }

        # Add helpful context when pending DTCs exist
        if pending_dtcs:
            data["note"] = (
                "Pending DTCs (Mode 07) are faults detected ONCE during the current/last drive cycle. "
                "They have NOT yet triggered the check engine light. "
                "If the same fault occurs again, they become confirmed DTCs (Mode 03)."
            )

            # Provide comparison with confirmed DTCs
            if confirmed_dtcs:
                data["confirmed_dtcs_also_present"] = True
                data["confirmed_count"] = len(confirmed_dtcs)
                data["suggestion"] = (
                    f"You have {len(pending_dtcs)} pending code(s) AND {len(confirmed_dtcs)} confirmed code(s). "
                    "Use obd_get_dtcs() to see the confirmed codes that triggered the check engine light."
                )
            else:
                data["confirmed_dtcs_also_present"] = False
                data["suggestion"] = (
                    "These are pending only - check engine light is NOT on (yet). "
                    "Monitor with test drive. If faults repeat, they'll become confirmed."
                )

        status = manager.get_status()
        return OBDResponse(
            ok=True,
            data=data,
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


def get_freeze_frame(connection, manager, dtc_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Get freeze frame data for a specific DTC.

    Freeze frame is a snapshot of sensor values at the moment a DTC was triggered.

    Args:
        connection: OBD connection object (reserved for future implementation)
        manager: OBDConnectionManager instance (reserved for future implementation)
        dtc_code: Optional DTC code (e.g., "P0171")

    Returns:
        dict: OBDResponse with freeze frame data (not yet implemented)

    Note:
        This is a stub implementation. Mode 02 freeze frame support requires
        custom OBD command implementation and is planned for a future release.
        Parameters are reserved for future use to maintain API compatibility.
    """
    # Freeze frame is Mode 02
    # Parameters are intentionally unused - reserved for future implementation
    _ = connection  # Suppress unused parameter warning
    _ = manager     # Suppress unused parameter warning

    # Build error message based on whether specific DTC was requested
    if dtc_code:
        message = f"Freeze frame support for DTC '{dtc_code}' requires custom Mode 02 implementation"
    else:
        message = "Freeze frame support requires custom Mode 02 implementation"

    return OBDResponse(
        ok=False,
        errors=[ErrorInfo(
            type=OBDErrorType.UNSUPPORTED_COMMAND.value,
            message=message,
            suggestion="This feature is planned for future implementation"
        )]
    ).to_dict()


def get_readiness(connection, manager) -> Dict[str, Any]:
    """
    Get emission readiness monitor status.

    Shows which OBD monitors have completed their self-diagnostic tests.
    Returns comprehensive status for both continuous monitors (misfire, fuel system,
    components) and non-continuous monitors (catalyst, EVAP, O2 sensors, etc.).

    Monitors are different for spark ignition (gasoline) vs compression ignition (diesel).

    Args:
        connection: OBD connection object
        manager: OBDConnectionManager instance

    Returns:
        dict: OBDResponse with readiness status including:
            - MIL status and DTC count
            - Overall readiness status (ready/not_ready/unknown)
            - Ignition type (spark/compression)
            - Individual monitor status (available/complete for each)
            - Summary statistics (total, available, completed, incomplete)

    Example response:
        {
          "ok": true,
          "data": {
            "mil_on": false,
            "dtc_count": 0,
            "readiness_status": "ready",
            "readiness_message": "All available monitors complete - vehicle is ready for emission testing",
            "ignition_type": "spark",
            "monitors_summary": {
              "total": 11,
              "available": 8,
              "completed": 8,
              "incomplete": 0
            },
            "continuous_monitors": {
              "MISFIRE_MONITORING": {"available": true, "complete": true},
              "FUEL_SYSTEM_MONITORING": {"available": true, "complete": true},
              "COMPONENT_MONITORING": {"available": true, "complete": true}
            },
            "non_continuous_monitors": {
              "CATALYST_MONITORING": {"available": true, "complete": true},
              "EVAPORATIVE_SYSTEM_MONITORING": {"available": true, "complete": true},
              ...
            }
          }
        }
    """
    try:
        # Check if OBD library is available (for non-mock mode)
        if not OBD_AVAILABLE or obd is None:
            return OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=OBDErrorType.UNSUPPORTED_COMMAND.value,
                    message="OBD library not available - cannot query readiness status"
                )]
            ).to_dict()

        # Get readiness status using Mode 01 PID 01 (STATUS command)
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

        # Parse individual monitor status
        monitors = parse_readiness_monitors(status_value)

        # Calculate readiness summary
        all_monitors = {**monitors["continuous_monitors"], **monitors["non_continuous_monitors"]}
        total_monitors = len(all_monitors)
        completed_monitors = sum(1 for m in all_monitors.values() if m["complete"])
        available_monitors = sum(1 for m in all_monitors.values() if m["available"])

        # Determine overall readiness status
        if total_monitors == 0:
            readiness_status = "unknown"
            readiness_message = "No monitor data available"
        elif completed_monitors == available_monitors and available_monitors > 0:
            readiness_status = "ready"
            readiness_message = "All available monitors complete - vehicle is ready for emission testing"
        else:
            readiness_status = "not_ready"
            incomplete_count = available_monitors - completed_monitors
            readiness_message = f"{incomplete_count} monitor(s) not yet complete - drive cycle required"

        status = manager.get_status()
        return OBDResponse(
            ok=True,
            data={
                "mil_on": mil_on,
                "dtc_count": dtc_count,
                "readiness_status": readiness_status,
                "readiness_message": readiness_message,
                "ignition_type": monitors["ignition_type"],
                "monitors_summary": {
                    "total": total_monitors,
                    "available": available_monitors,
                    "completed": completed_monitors,
                    "incomplete": available_monitors - completed_monitors
                },
                "continuous_monitors": monitors["continuous_monitors"],
                "non_continuous_monitors": monitors["non_continuous_monitors"]
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
