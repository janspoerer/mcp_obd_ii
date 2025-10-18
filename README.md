# MCP OBD-II Server

Model Context Protocol (MCP) server for reading PIDs (Parameter IDs) from cars using the OBD-II (On-Board Diagnostics II) standard.

## Features

- Connect to OBD-II adapters via serial/USB/Bluetooth
- Read sensor data (RPM, speed, temperature, fuel, emissions, etc.)
- Query individual PIDs or batches of PIDs
- List supported PIDs for your vehicle
- Get diagnostic trouble codes (DTCs)
- Auto-detect port, baud rate, and protocol
- Mock mode for testing without hardware

## Requirements

- Python 3.10+
- ELM327-compatible OBD-II adapter
- Vehicle with OBD-II port (US 1996+, Euro 2001+)

## Installation

Create a virtual environment. You will use the Python path from there later in the MCP server config:
```
python -m venv .venv
```

If not yet activated, activate the virtual environment that you have just created:
```
source .venv/bin/activate
```

```bash
cd mcp_obd_ii
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

And then enable your AI agent (such as Claude Code) to use the MCP by putting a `.mcp.json` file into the folder where you are executing the agent from:

```
{
    "mcpServers": {
        "mcp_obd_ii": {
            "type": "stdio",
            "command": "/Users/janspoerer/code/miscellaneous/obd_ii/mcp_obd_ii/.venv/bin/python",
            "args": ["-m", "mcp_obd_ii"],
            "env": {
                "PYTHONPATH": "/Users/janspoerer/code/miscellaneous/obd_ii/mcp_obd_ii/src"
            }
        }
    }
}

```

## Available Tools

### Connection Management

- `obd_connect` - Establish OBD connection (auto-detect or manual config)
- `obd_disconnect` - Close connection gracefully
- `obd_status` - Get connection status and vehicle info

### Basic Queries

- `obd_query_pid` - Query single PID by name (e.g., "RPM", "SPEED")
- `obd_query_multiple` - Query multiple PIDs efficiently
- `obd_list_supported` - List all PIDs supported by your vehicle

### Category Queries

- `obd_engine_data` - Get all engine-related data
- `obd_fuel_system` - Get all fuel system data

## Architecture

```
mcp_obd_ii/
├── __init__.py              # Package exports
├── __main__.py              # FastMCP server & tools
├── connection_manager.py    # Singleton OBD connection
├── decorators.py            # Error handling & tool wrappers
├── helpers.py               # Query & formatting utilities
└── response_models.py       # Data structures & enums
```

## Dependencies

- `mcp` - Model Context Protocol SDK
- `pyserial` - Serial port communication
- `obd` - Python OBD-II library (pyobd fork)
