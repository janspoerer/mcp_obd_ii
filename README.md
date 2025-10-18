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
    - Recommendation: USB-based, not Bluethooth, as USB tends to be more stable.
    - This one is good: Vgate vLinker FS OBD2 USB Adapter for Scan HS/MS-CAN Car Switch
        - Use either this Amazon affilate link (USA): [https://amzn.to/3WP2pAg](https://amzn.to/3WP2pAg), Germany: [https://amzn.to/4hiAjXz](https://amzn.to/4hiAjXz)
        - Or this ordinary link, if you prefer: [https://www.amazon.de/dp/B094Z7PBLS?ref=ppx_yo2ov_dt_b_fed_asin_title](https://www.amazon.de/dp/B094Z7PBLS?ref=ppx_yo2ov_dt_b_fed_asin_title)
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

```json
{
    "mcpServers": {
        "mcp_obd_ii": {
            "type": "stdio",
            "command": "/path/to/your/mcp_obd_ii/.venv/bin/python",
            "args": ["-m", "mcp_obd_ii"],
            "env": {
                "PYTHONPATH": "/path/to/your/mcp_obd_ii/src"
            }
        }
    }
}
```

Replace `/path/to/your/mcp_obd_ii` with the actual path to your installation.

Start Claude Code with this MCP server:
```bash
claude --strict-mcp-config --mcp-config /path/to/your/.mcp.json
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

### Diagnostic Trouble Codes (DTCs)

- `obd_get_dtcs` - Get current diagnostic trouble codes
- `obd_clear_dtcs` - Clear all DTCs (⚠️ WARNING: Destructive operation)
- `obd_get_pending_dtcs` - Get pending (not yet confirmed) DTCs
- `obd_get_freeze_frame` - Get freeze frame data for a DTC
- `obd_get_readiness` - Get emission readiness monitor status

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

## Development Notes

### Mock Mode

Mock mode allows testing and development without physical OBD-II hardware. It returns fake sensor data for basic PIDs.

**Enable mock mode:**
```json
{
    "mcpServers": {
        "mcp_obd_ii": {
            "type": "stdio",
            "command": "/path/to/your/mcp_obd_ii/.venv/bin/python",
            "args": ["-m", "mcp_obd_ii"],
            "env": {
                "PYTHONPATH": "/path/to/your/mcp_obd_ii/src",
                "MOCK_OBD": "true"
            }
        }
    }
}
```

**What's supported in mock mode:**
- ✅ Basic PIDs: RPM, SPEED, COOLANT_TEMP, ENGINE_LOAD, THROTTLE_POS, INTAKE_TEMP, MAF, FUEL_LEVEL
- ✅ Connection management: connect, disconnect, status
- ❌ DTCs: Not supported (returns error)
- ❌ Readiness monitors: Not supported
- ❌ Freeze frames: Not supported

Mock mode activates automatically if the `obd` library is not installed.

**Use cases:**
- Testing MCP integration without a car
- CI/CD pipelines
- Development and debugging
- Demonstrations
