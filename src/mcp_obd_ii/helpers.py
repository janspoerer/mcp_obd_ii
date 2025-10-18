"""
Helper functions for OBD-II operations.

Provides query helpers, response formatting, and validation utilities.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False
    obd = None

from .connection_manager import OBDConnectionManager
from .response_models import PIDData, PID_CATEGORIES


logger = logging.getLogger(__name__)


def format_pid_response(response, include_raw: bool = False) -> Dict[str, Any]:
    """
    Format OBD response into standardized PID data structure.

    Args:
        response: OBD response object
        include_raw: Include raw hex response data

    Returns:
        dict: Formatted PID data
    """
    if response is None or response.is_null():
        return None

    pid_data = {
        "pid": response.command.name,
        "description": response.command.desc,
        "value": format_value(response.value),
        "timestamp": datetime.now().isoformat()
    }

    # Add unit if available
    unit_str = parse_unit(response.value)
    if unit_str:
        pid_data["unit"] = unit_str

    # Add raw data if requested
    if include_raw and response.messages:
        raw_values = []
        for msg in response.messages:
            if hasattr(msg, 'data'):
                raw_values.append(msg.data.hex().upper())
        if raw_values:
            pid_data["raw_value"] = " ".join(raw_values)

    return pid_data


def format_value(value: Any) -> Any:
    """
    Format value for JSON serialization.

    Handles Pint quantities, special objects, etc.

    Args:
        value: Raw value from OBD response

    Returns:
        JSON-serializable value
    """
    if value is None:
        return None

    # Handle Pint Quantity objects
    if hasattr(value, 'magnitude'):
        return float(value.magnitude)

    # Handle special OBD objects
    if hasattr(value, '__dict__'):
        # Status object
        if hasattr(value, 'MIL'):
            return {
                "MIL": value.MIL,
                "DTC_count": value.DTC_count,
                "ignition_type": getattr(value, 'ignition_type', None)
            }

    # Handle lists/tuples
    if isinstance(value, (list, tuple)):
        return [format_value(v) for v in value]

    # Primitive types
    if isinstance(value, (int, float, str, bool)):
        return value

    # Fallback to string
    return str(value)


def parse_unit(value: Any) -> Optional[str]:
    """
    Parse unit from Pint Quantity or return None.

    Args:
        value: Value that may contain unit information

    Returns:
        str: Unit name or None
    """
    if value is None:
        return None

    # Pint Quantity
    if hasattr(value, 'units'):
        unit_str = str(value.units)
        # Clean up unit formatting
        unit_str = unit_str.replace('_', ' ')
        return unit_str

    return None


def safe_query(connection, command_name: str, include_raw: bool = False) -> Optional[Dict[str, Any]]:
    """
    Safely query a PID by name.

    Args:
        connection: OBD connection object
        command_name: PID name (e.g., "RPM", "SPEED")
        include_raw: Include raw hex data

    Returns:
        dict: Formatted PID data or None if failed
    """
    if not OBD_AVAILABLE:
        logger.error("obd library not available")
        return None

    try:
        # Get command by name
        if not hasattr(obd.commands, command_name):
            logger.warning(f"Unknown command: {command_name}")
            return None

        command = getattr(obd.commands, command_name)

        # Query the command
        response = connection.query(command)

        # Format and return
        return format_pid_response(response, include_raw=include_raw)

    except Exception as e:
        logger.error(f"Error querying {command_name}: {e}")
        return None


def batch_query(connection, command_names: List[str], include_raw: bool = False) -> List[Dict[str, Any]]:
    """
    Query multiple PIDs efficiently.

    Args:
        connection: OBD connection object
        command_names: List of PID names
        include_raw: Include raw hex data

    Returns:
        list: List of formatted PID data (None for failed queries)
    """
    results = []
    for cmd_name in command_names:
        result = safe_query(connection, cmd_name, include_raw=include_raw)
        if result is not None:
            results.append(result)
    return results


def query_by_category(connection, category: str, include_raw: bool = False) -> Dict[str, Any]:
    """
    Query all PIDs in a category.

    Args:
        connection: OBD connection object
        category: Category name (e.g., "engine", "fuel", "emissions")
        include_raw: Include raw hex data

    Returns:
        dict: Category name and list of PID results
    """
    if category not in PID_CATEGORIES:
        logger.warning(f"Unknown category: {category}")
        return {
            "category": category,
            "error": "Unknown category",
            "pids": []
        }

    pid_names = PID_CATEGORIES[category]
    results = batch_query(connection, pid_names, include_raw=include_raw)

    return {
        "category": category,
        "pids": results,
        "count": len(results)
    }


def validate_pid_name(name: str) -> bool:
    """
    Validate PID name exists in obd.commands.

    Args:
        name: PID name to validate

    Returns:
        bool: True if valid
    """
    if not OBD_AVAILABLE:
        return False

    return hasattr(obd.commands, name)


def get_pids_by_category(category: str) -> List[str]:
    """
    Get list of PID names for a category.

    Args:
        category: Category name

    Returns:
        list: PID names
    """
    return PID_CATEGORIES.get(category, [])


def get_all_categories() -> List[str]:
    """
    Get list of all available categories.

    Returns:
        list: Category names
    """
    return list(PID_CATEGORIES.keys())


def get_vehicle_metadata(connection) -> Dict[str, Any]:
    """
    Get vehicle identification metadata.

    Args:
        connection: OBD connection object

    Returns:
        dict: Vehicle metadata (VIN, calibration ID, etc.)
    """
    metadata = {}

    if not OBD_AVAILABLE:
        return metadata

    # Try to get VIN (Mode 09, PID 02)
    try:
        if hasattr(obd.commands, 'VIN'):
            vin_response = connection.query(obd.commands.VIN)
            if not vin_response.is_null():
                metadata['vin'] = str(vin_response.value)
    except Exception as e:
        logger.debug(f"Could not retrieve VIN: {e}")

    # Try to get ECU name (Mode 09, PID 0A)
    try:
        if hasattr(obd.commands, 'ECU_NAME'):
            ecu_response = connection.query(obd.commands.ECU_NAME)
            if not ecu_response.is_null():
                metadata['ecu_name'] = str(ecu_response.value)
    except Exception as e:
        logger.debug(f"Could not retrieve ECU name: {e}")

    # Try to get calibration ID (Mode 09, PID 04)
    try:
        if hasattr(obd.commands, 'CALIBRATION_ID'):
            cal_response = connection.query(obd.commands.CALIBRATION_ID)
            if not cal_response.is_null():
                metadata['calibration_id'] = str(cal_response.value)
    except Exception as e:
        logger.debug(f"Could not retrieve calibration ID: {e}")

    return metadata


def format_status_response(connection) -> Dict[str, Any]:
    """
    Format comprehensive connection status.

    Args:
        connection: OBD connection object

    Returns:
        dict: Status information
    """
    manager = OBDConnectionManager.get_instance()
    status = manager.get_status()

    # Add supported commands list
    supported = manager.get_supported_commands()
    status['supported_commands'] = supported
    status['supported_commands_count'] = len(supported)

    return status


def format_dtc_response(codes: List) -> List[Dict[str, str]]:
    """
    Format diagnostic trouble codes.

    Args:
        codes: List of DTC tuples from OBD response

    Returns:
        list: Formatted DTC information
    """
    if not codes:
        return []

    formatted = []
    for code_tuple in codes:
        if len(code_tuple) >= 2:
            formatted.append({
                "code": code_tuple[0],
                "description": code_tuple[1]
            })
        else:
            formatted.append({
                "code": str(code_tuple),
                "description": "Unknown"
            })

    return formatted
