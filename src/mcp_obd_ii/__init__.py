"""
MCP OBD-II Server

Model Context Protocol server for reading PIDs from cars using OBD-II standard.
"""

import logging

from .connection_manager import OBDConnectionManager
from .response_models import (
    ConnectionState,
    OBDErrorType,
    OBDResponse,
    PIDData,
    ConnectionConfig,
    PID_CATEGORIES
)
from .decorators import (
    connection_required,
    tool_envelope,
    log_execution
)
from . import helpers

__version__ = "0.1.0"

# Configure logging
logger = logging.getLogger(__name__)
logger.warning(f"mcp_obd_ii version {__version__}")

__all__ = [
    "OBDConnectionManager",
    "ConnectionState",
    "OBDErrorType",
    "OBDResponse",
    "PIDData",
    "ConnectionConfig",
    "PID_CATEGORIES",
    "connection_required",
    "tool_envelope",
    "log_execution",
    "helpers"
]
