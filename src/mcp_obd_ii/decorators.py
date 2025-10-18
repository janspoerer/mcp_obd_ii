"""
Decorators for MCP OBD-II tools.

Provides error handling, connection management, and logging decorators.
"""

import functools
import logging
import time
import json
from typing import Callable

from .connection_manager import OBDConnectionManager
from .response_models import OBDResponse, ErrorInfo, Metadata, OBDErrorType


logger = logging.getLogger(__name__)


def connection_required(func: Callable) -> Callable:
    """
    Ensure OBD connection is active before tool execution.

    If no connection exists, attempts auto-connect. If that fails, returns
    an error response. This decorator should be applied after @tool_envelope.

    Usage:
        @mcp.tool()
        @tool_envelope
        @connection_required
        async def my_tool(...):
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        manager = OBDConnectionManager.get_instance()

        if not manager.is_connected():
            logger.warning("No OBD connection, attempting auto-connect")

            # Try auto-connect
            try:
                if manager.connect():
                    logger.info("Auto-connect successful")
                else:
                    error_response = OBDResponse(
                        ok=False,
                        errors=[ErrorInfo(
                            type=OBDErrorType.NOT_CONNECTED.value,
                            message="No OBD connection and auto-connect failed",
                            suggestion="Call obd_connect() with specific port/protocol, or check hardware connection"
                        )]
                    )
                    return error_response.to_dict()
            except Exception as e:
                logger.exception("Auto-connect failed with exception")
                error_response = OBDResponse(
                    ok=False,
                    errors=[ErrorInfo(
                        type=OBDErrorType.CONNECTION_FAILED.value,
                        message=f"Auto-connect failed: {str(e)}",
                        suggestion="Check that OBD adapter is connected and vehicle is running"
                    )]
                )
                return error_response.to_dict()

        return await func(*args, **kwargs)

    return wrapper


def tool_envelope(func: Callable) -> Callable:
    """
    Wrap tool execution in standardized response envelope.

    Handles:
    - Execution timing
    - Exception catching and formatting
    - Response serialization to JSON
    - Metadata injection

    This decorator should be the outermost decorator (after @mcp.tool()).

    Usage:
        @mcp.tool()
        @tool_envelope
        async def my_tool(...):
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            # Execute the tool function
            result = await func(*args, **kwargs)

            # Calculate execution time
            exec_time = (time.time() - start_time) * 1000

            # If result is already a dict (from OBDResponse.to_dict()), enhance it
            if isinstance(result, dict):
                if 'metadata' not in result:
                    result['metadata'] = {}
                result['metadata']['execution_time_ms'] = round(exec_time, 2)

                # Serialize to JSON
                return json.dumps(result, default=str, ensure_ascii=False)

            # If result is OBDResponse object
            elif hasattr(result, 'to_dict'):
                result_dict = result.to_dict()
                result_dict['metadata']['execution_time_ms'] = round(exec_time, 2)
                return json.dumps(result_dict, default=str, ensure_ascii=False)

            # If result is already a JSON string, try to parse and enhance
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict):
                        if 'metadata' not in parsed:
                            parsed['metadata'] = {}
                        parsed['metadata']['execution_time_ms'] = round(exec_time, 2)
                        return json.dumps(parsed, default=str, ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
                return result

            # Fallback: wrap in basic response
            response = OBDResponse(
                ok=True,
                data={"result": result},
                metadata=Metadata(execution_time_ms=round(exec_time, 2))
            )
            return json.dumps(response.to_dict(), default=str, ensure_ascii=False)

        except Exception as e:
            logger.exception(f"Tool error in {func.__name__}")

            # Classify the error
            error_type = classify_error(e)

            exec_time = (time.time() - start_time) * 1000

            error_response = OBDResponse(
                ok=False,
                errors=[ErrorInfo(
                    type=error_type.value,
                    message=str(e),
                    suggestion=get_error_suggestion(error_type),
                    context={"tool": func.__name__}
                )],
                metadata=Metadata(execution_time_ms=round(exec_time, 2))
            )

            return json.dumps(error_response.to_dict(), default=str, ensure_ascii=False)

    return wrapper


def log_execution(func: Callable) -> Callable:
    """
    Log tool execution for debugging.

    Logs tool name, arguments, and completion status.

    Usage:
        @mcp.tool()
        @tool_envelope
        @log_execution
        async def my_tool(...):
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Log sanitized arguments (avoid logging sensitive data)
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in ['password', 'token']}
        logger.info(f"Executing {func.__name__} with kwargs={sanitized_kwargs}")

        result = await func(*args, **kwargs)

        logger.info(f"Completed {func.__name__}")
        return result

    return wrapper


def classify_error(error: Exception) -> OBDErrorType:
    """
    Classify exception into OBD error type.

    Args:
        error: Exception to classify

    Returns:
        OBDErrorType: Classified error type
    """
    error_str = str(error).lower()
    error_type_name = type(error).__name__.lower()

    # Serial/connection errors
    if 'serial' in error_type_name or 'serial' in error_str:
        return OBDErrorType.SERIAL_ERROR
    if 'timeout' in error_type_name or 'timeout' in error_str:
        return OBDErrorType.TIMEOUT
    if 'disconnect' in error_str or 'not connected' in error_str:
        return OBDErrorType.DEVICE_DISCONNECTED
    if 'connection' in error_str or 'connect' in error_str:
        return OBDErrorType.CONNECTION_FAILED

    # OBD-specific errors
    if 'not supported' in error_str or 'unsupported' in error_str:
        return OBDErrorType.UNSUPPORTED_COMMAND
    if 'decode' in error_str or 'invalid response' in error_str:
        return OBDErrorType.DECODER_ERROR
    if 'custom' in error_str and 'command' in error_str:
        return OBDErrorType.CUSTOM_COMMAND_ERROR

    # Default
    return OBDErrorType.UNKNOWN_ERROR


def get_error_suggestion(error_type: OBDErrorType) -> str:
    """
    Get helpful suggestion for error type.

    Args:
        error_type: Classified error type

    Returns:
        str: Helpful suggestion for user
    """
    suggestions = {
        OBDErrorType.NOT_CONNECTED: "Call obd_connect() to establish connection",
        OBDErrorType.CONNECTION_FAILED: "Check OBD adapter is connected and vehicle ignition is on",
        OBDErrorType.DEVICE_DISCONNECTED: "Reconnect OBD adapter and call obd_connect() again",
        OBDErrorType.UNSUPPORTED_COMMAND: "Use obd_list_supported() to see available PIDs for your vehicle",
        OBDErrorType.TIMEOUT: "Ensure vehicle engine is running and adapter is responding",
        OBDErrorType.SERIAL_ERROR: "Check serial port permissions and adapter connection",
        OBDErrorType.DECODER_ERROR: "This PID may not be compatible with your vehicle",
        OBDErrorType.CUSTOM_COMMAND_ERROR: "Verify custom command parameters (mode, PID, bytes)",
        OBDErrorType.UNKNOWN_ERROR: "Check logs for more details"
    }
    return suggestions.get(error_type, "Please check the error message for details")
