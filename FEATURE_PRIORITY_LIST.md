# MCP OBD-II Feature Priority List

This document outlines all planned features for the MCP OBD-II server, organized by implementation priority and complexity.

## Current Status

### ✅ Implemented Features
- Connection management (auto-detection of port, baudrate, protocol)
- Single PID querying (`obd_query_pid`)
- Batch PID querying (`obd_query_multiple`)
- List supported PIDs (`obd_list_supported`)
- Engine data category query (`obd_engine_data`)
- Fuel system category query (`obd_fuel_system`)
- Vehicle metadata (VIN, ECU name, calibration ID)
- Mock mode for testing without hardware
- Structured error handling and response envelopes

### ❌ Critical Gaps
- **No DTC (Diagnostic Trouble Code) support** - Despite README claim, no tools implement this
- **No freeze frame data** - Cannot see sensor values when fault occurred
- **No readiness monitors** - Cannot check emission test readiness
- **Missing category queries** - Only 2 of 7 categories implemented
- **No real-time monitoring** - Cannot stream data during driving
- **No data export** - Cannot save diagnostic sessions

---

## Phase 1: Critical Features (Makes Tool Actually Useful)

These features are ESSENTIAL for basic professional use. Without these, the tool cannot perform the primary function mechanics need from an OBD-II scanner.

### 1.1 Basic DTC Operations (HIGHEST PRIORITY) 🚨

#### Get Current DTCs (`obd_get_dtcs`)
**Mode 03** - Read active diagnostic trouble codes
- Return code (e.g., "P0171"), description, and status
- Show DTC count
- Indicate MIL (Malfunction Indicator Lamp / Check Engine Light) status
- Show which DTCs commanded the MIL on

**Implementation:** ~50 lines using `obd.commands.GET_DTC`

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Clear DTCs (`obd_clear_dtcs`)
**Mode 04** - Clear all diagnostic trouble codes
- Clear current, pending, and freeze frame data
- Reset MIL (turn off check engine light)
- Reset readiness monitors (sets them to "not ready")
- Clear distance/time counters
- **Warning to user:** This erases diagnostic data permanently

**Implementation:** ~30 lines using `obd.commands.CLEAR_DTC`

**Security:** ⚠️ MEDIUM RISK - Destructive write operation. Permanently erases DTCs and freeze frames. Can hide problems leading to expensive damage. May constitute fraud if used to pass emissions testing. Requires explicit warnings and user confirmation.

#### Get Pending DTCs (`obd_get_pending_dtcs`)
**Mode 07** - Read codes detected but not yet confirmed
- Codes that haven't lit the check engine light yet
- Useful for catching intermittent problems early
- Helps predict what might fail soon

**Implementation:** ~40 lines, similar to GET_DTC

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

### 1.2 Freeze Frame Data 🔥

#### Get Freeze Frame (`obd_get_freeze_frame`)
**Mode 02** - Retrieve sensor snapshot when DTC was set
- All sensor values at moment DTC triggered
- Typically includes:
  - Engine RPM
  - Vehicle speed
  - Coolant temperature
  - Engine load
  - Short-term fuel trim (Bank 1 & 2)
  - Long-term fuel trim (Bank 1 & 2)
  - Intake manifold pressure
  - Throttle position
  - MAF sensor reading
  - O2 sensor voltages
  - Time since engine start
- Accept DTC code as parameter or return for primary DTC
- Match each freeze frame to its triggering DTC

**Implementation:** ~80 lines, reuse existing PID formatting helpers

**Why Critical:** Without freeze frame, diagnosing intermittent problems is nearly impossible. You can't see what conditions existed when the fault occurred.

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

### 1.3 Readiness Monitors / I/M Readiness

#### Get Readiness Status (`obd_get_readiness`)
**Mode 01 PID 01** - Check emission test readiness
- Essential for emission testing compliance
- Shows which self-diagnostic tests have completed

**Continuous Monitors** (always running):
- Misfire detection
- Fuel system monitoring
- Comprehensive component monitoring

**Non-Continuous Monitors** (run under specific conditions):
- Catalyst efficiency
- Heated catalyst
- Evaporative system (EVAP)
- Secondary air system
- A/C refrigerant
- Oxygen sensor
- Oxygen sensor heater
- EGR system (Exhaust Gas Recirculation)

**For each monitor show:**
- `supported` - This vehicle has this monitor
- `complete` - Monitor test has run and passed
- `incomplete` - Monitor hasn't run yet this drive cycle

**Implementation:** ~60 lines using `obd.commands.STATUS`

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

### 1.4 MIL Status & Counters

#### Get MIL Status (`obd_get_mil_status`)
- Current MIL on/off state
- Distance traveled with MIL on (`DISTANCE_W_MIL`)
- Time with MIL activated (`TIME_WITH_MIL`)
- Flashing vs steady (flashing = severe misfire)

**Implementation:** ~40 lines using existing commands

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Get DTC Clear History (`obd_get_dtc_clear_history`)
- Warm-up cycles since codes cleared (`WARMUPS_SINCE_DTC_CLEAR`)
- Distance traveled since cleared (`DISTANCE_SINCE_DTC_CLEAR`)
- Time since cleared (`TIME_SINCE_DTC_CLEAR`)

**Implementation:** ~30 lines using existing commands

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

### 1.5 Custom PID Support ⚡

**IMPORTANT:** Custom PID support is technically trivial to implement but challenging to use effectively.

#### Query Custom PID (`obd_query_custom_pid`)
Query manufacturer-specific or non-standard PIDs
```python
obd_query_custom_pid(
    mode="22",              # Hex mode (e.g., "22" for manufacturer-specific)
    pid="F190",             # Hex PID code
    formula="(A*256+B)/100-40",  # Transformation formula
    unit="celsius",         # Unit of measurement
    description="Transmission fluid temperature",
    num_bytes=2             # Expected response length
)
```

**Examples:**
- Mercedes transmission temp: Mode 22, PID F190
- BMW coolant temp: Mode 22, PID 0107
- Turbo boost pressure: Varies by manufacturer

**Implementation Complexity:** ~50 lines of code

**Real Challenges:**
1. **PID Discovery** - Manufacturers don't publish these PIDs
   - Requires reverse engineering or community research
   - Forums and enthusiast communities share findings
   - Commercial tools charge $500-5000 for manufacturer databases

2. **Formula Discovery** - Even knowing the PID exists isn't enough
   - Must figure out scaling/offset by trial and error
   - Compare known values with raw bytes
   - Different manufacturers use different formulas

3. **Legal/Access Issues**
   - Some manufacturers encrypt or authenticate access
   - Commercial scanners have legal agreements for data
   - Artificial scarcity protects business models

4. **Protocol Variations**
   - BMW: ISTA/D protocol
   - VAG (VW/Audi): UDS (Unified Diagnostic Services)
   - Mercedes: SCN coding
   - May require different communication layers beyond OBD-II

**Why This is Phase 1:** The implementation is simple, and it unblocks your Mercedes transmission fluid use case immediately. The hard part is finding the right PID/formula, but that's a user research problem, not a coding problem.

**Security:** ⚠️ LOW TO HIGH RISK (Mode-Dependent) - MUST restrict to read-only modes (01, 02, 03, 07, 09, 0A, 22). Write modes (2E, 31, 3D, 3E, 27, 28, 34-37) MUST BE BLOCKED to prevent ECU damage, bricking, or unauthorized modifications. Implement whitelist validation. Incorrect PIDs may cause ECU crashes.

---

## Phase 2: Professional Features (Makes Tool Competitive)

These features elevate the tool from "basic" to "professional-grade" and enable serious diagnostic work.

### 2.1 Enhanced DTC Information

#### Get Permanent DTCs (`obd_get_permanent_dtcs`)
**Mode 0A** - DTCs that cannot be cleared by user
- Only clear when ECU confirms repair successful
- Required for emission testing compliance
- Introduced in OBD-II after 2010

**Implementation:** ~40 lines

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Enhanced DTC Metadata
For each DTC, provide rich information:
- **Code** - e.g., "P0171"
- **Description** - e.g., "System Too Lean (Bank 1)"
- **Severity** - Critical/Warning/Information
- **System** - Powertrain/Chassis/Body/Network
- **Subsystem** - Fuel/Ignition/Emissions/etc.
- **Type Prefix**:
  - `P` = Powertrain
  - `C` = Chassis
  - `B` = Body
  - `U` = Network/Communications
- **Code Type** (second digit):
  - `0` = SAE standard code
  - `1`, `2`, `3` = Manufacturer-specific
- **Common Causes** - List of typical root causes
- **Related Codes** - Other DTCs often seen together
- **Affected Systems** - What systems are impacted
- **Repair Priority** - Urgency of repair

**Implementation:** Requires building/importing a DTC database (~500 lines + JSON data)

**Security:** ✅ SAFE - Data enrichment only, no vehicle communication

#### DTC Status Bits
For each DTC, provide detailed status flags:
- `confirmed` - DTC has matured and lit the MIL
- `pending` - Detected once, not confirmed yet
- `test_failed_since_clear` - Test has failed this drive cycle
- `test_not_completed` - Test hasn't run this cycle
- `mil_commanded` - This DTC commanded MIL on
- `warning_lamp_commanded` - Alternate warning lamp status

**Implementation:** ~60 lines parsing status response

**Security:** ✅ SAFE - Read-only operation, data parsing only

### 2.2 Mode 06 - On-Board Monitoring Test Results

#### Get Mode 06 Test Results (`obd_get_test_results`)
**Mode 06** - Component test values and limits
- Shows actual measured values vs. acceptable ranges
- Identifies degrading components before failure
- Verifies repairs without waiting for monitors to complete

**For each test provide:**
- **Test ID** - Which component/system was tested
- **Component ID** - Specific component identifier
- **Test Value** - Measured value during test
- **Test Limit (Min)** - Lower acceptable limit
- **Test Limit (Max)** - Upper acceptable limit
- **Test Result** - Pass/Fail/Incomplete

**Common Mode 06 Tests:**
- O2 sensor response time
- Catalyst efficiency ratios
- EGR flow rates
- EVAP leak test results
- Misfire counts by cylinder
- Fuel system pressure tests

**Implementation:** ~150 lines (Mode 06 is complex and manufacturer-specific)

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

### 2.3 Complete Category Queries

Complete the missing category queries to match the PID_CATEGORIES structure:

#### Emissions Data (`obd_emissions_data`)
- All O2 sensor readings (Bank 1/2, Sensor 1/2/3/4)
- Catalyst temperatures
- EGR status
- EVAP system status

**Implementation:** ~40 lines (copy pattern from engine/fuel queries)

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Status Data (`obd_status_data`)
- STATUS, STATUS_DRIVE_CYCLE
- DTC_STATUS
- OBD_COMPLIANCE
- Monitor O2 sensor data

**Implementation:** ~40 lines

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Air System Data (`obd_air_system_data`)
- AIR_STATUS
- Multiple throttle position sensors
- Accelerator positions
- Commanded throttle actuator
- Ambient air temperature

**Implementation:** ~40 lines

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Distance/Time Metrics (`obd_distance_time_data`)
- DISTANCE_W_MIL
- DISTANCE_SINCE_DTC_CLEAR
- WARMUPS_SINCE_DTC_CLEAR
- TIME_SINCE_DTC_CLEAR
- TIME_WITH_MIL

**Implementation:** ~40 lines

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

### 2.4 Data Export & Logging

#### Export Diagnostic Report (`obd_export_diagnostic_report`)
Generate comprehensive diagnostic snapshot:
- All current DTCs + freeze frames
- All readiness monitors status
- Critical sensor readings
- Vehicle information (VIN, calibration, protocol, etc.)
- Timestamp and odometer reading

**Export Formats:**
- JSON (default - for programmatic processing)
- CSV (for spreadsheet analysis)
- Markdown (human-readable)

**Implementation:** ~120 lines

**Security:** ✅ SAFE - Local file operations only, no vehicle communication

#### Save Custom PID Definitions (`obd_save_custom_pid`)
Allow users to save custom PID definitions for reuse:
```python
obd_save_custom_pid(
    name="TRANS_FLUID_TEMP",
    mode="22",
    pid="F190",
    formula="(A*256+B)/100-40",
    unit="celsius",
    description="Transmission fluid temperature",
    manufacturer="Mercedes",
    models=["W211", "W212"]
)
```

Store in JSON file for persistence.

**Implementation:** ~80 lines

**Security:** ✅ SAFE - Local file operations only, no vehicle communication. Validate mode safety before saving.

#### Query Saved Custom PID (`obd_query_saved_pid`)
Query previously saved custom PID by name:
```python
obd_query_saved_pid(name="TRANS_FLUID_TEMP")
```

**Implementation:** ~40 lines

**Security:** ⚠️ LOW TO HIGH RISK - Inherits safety from saved PID definition. Only safe if saved PID uses read-only mode. Validate mode before querying.

### 2.5 Enhanced O2 Sensor & Fuel Trim Analysis

#### O2 Sensor Detailed Data (`obd_get_o2_sensors`)
Comprehensive O2 sensor monitoring:
- Voltage readings (Bank 1/2, Sensor 1/2/3/4)
- Short-term fuel trim influence
- Response time
- Rich/lean toggles per minute
- Heater circuit status

**Implementation:** ~100 lines

**Security:** ✅ SAFE - Read-only operation, no risk to vehicle or data

#### Fuel Trim Analysis (`obd_analyze_fuel_trim`)
Analyze and interpret fuel trim values:
- Short-Term Fuel Trim (STFT) - Bank 1 and 2
- Long-Term Fuel Trim (LTFT) - Bank 1 and 2
- **Interpretation:**
  - Normal range: -10% to +10%
  - Positive = adding fuel (system running lean)
  - Negative = removing fuel (system running rich)
  - Warnings when out of range
- **Diagnosis hints:**
  - High STFT + high LTFT = chronic lean condition (vacuum leak, weak fuel pump)
  - Low STFT + low LTFT = chronic rich condition (leaking injector, bad MAF)

**Implementation:** ~80 lines with interpretation logic

**Security:** ✅ SAFE - Read-only operation with data analysis, no risk to vehicle

---

## Phase 3: Advanced Features (Makes Tool Exceptional)

These features provide capabilities found only in high-end professional scan tools.

### 3.1 Real-Time Data Streaming

#### Stream PIDs (`obd_stream_pids`)
Continuous PID reading for live monitoring:
- Configurable update rate (Hz)
- Select which PIDs to monitor
- Stream to stdout or file
- Duration or continuous mode

**Use Cases:**
- Watch RPM while revving engine
- Monitor fuel trims during test drive
- Track temperature changes over time
- Record sensor data during problem reproduction

**Implementation:** ~150 lines with async streaming

**Security:** ⚠️ MODERATE RISK - Read-only operation but potential driver distraction if used while driving. Add clear warnings against use while vehicle is moving.

#### Triggered Recording (`obd_record_on_condition`)
Start recording when condition is met:
```python
obd_record_on_condition(
    trigger="RPM > 3000",
    pids=["RPM", "MAF", "THROTTLE_POS"],
    duration=30  # seconds after trigger
)
```

**Implementation:** ~120 lines with condition parsing

**Security:** ⚠️ MODERATE RISK - Read-only operation but potential driver distraction. Warn against use while driving.

### 3.2 Enhanced Catalyst & EVAP Monitoring

#### Catalyst System Analysis (`obd_analyze_catalyst`)
- Pre-catalyst temperature
- Post-catalyst temperature
- Overheating warnings
- O2 sensor switching ratios
- Upstream vs downstream comparison
- Mode 06 efficiency test results

**Implementation:** ~100 lines

**Security:** ✅ SAFE - Read-only operation, data analysis only

#### EVAP System Monitoring (`obd_analyze_evap`)
- Purge valve status
- Vent valve status
- Fuel tank pressure
- Leak detection test results
- Gross leak vs small leak detection
- EVAP monitor completion status

**Implementation:** ~100 lines

**Security:** ✅ SAFE - Read-only operation, data analysis only

### 3.3 Multi-Module Scanning

#### Scan All ECUs (`obd_scan_all_modules`)
Scan beyond just the engine ECU:
- Engine Control Module (ECM)
- Transmission Control Module (TCM)
- Anti-lock Brake System (ABS)
- Airbag Control Module (SRS)
- Body Control Module (BCM)
- Climate Control
- Instrument Cluster

**Challenges:**
- Requires extended diagnostic protocols
- Not all modules accessible via standard OBD-II
- May need manufacturer-specific protocols

**Implementation:** ~200 lines + protocol support

**Security:** ✅ SAFE - Read-only operation (if restricted to read modes). May trigger temporary warning lights on some vehicles (normal diagnostic behavior).

### 3.4 Bi-Directional Control

#### Active Component Tests (`obd_test_component`)
Command specific components on/off for testing:
- EVAP purge solenoid
- EVAP vent valve
- Cooling fan (low/high speed)
- A/C compressor clutch
- Fuel pump
- Secondary air pump
- EGR valve

**Safety Considerations:**
- Warn user about active tests
- Only when engine is running (where applicable)
- Time limits on activation

**Implementation:** ~150 lines + safety checks

**Security:** 🚨 HIGH RISK - Physical danger (injury, fire), mechanical damage, crash risk. Activates physical components (fans, pumps, solenoids). REQUIRES extensive safety checks: engine state validation, vehicle must be stationary, timeout limits, explicit warnings. See safety section for full requirements. Recommend NOT implementing.

#### Cylinder Power Balance (`obd_cylinder_balance_test`)
Disable individual cylinders to test contribution:
- Identify weak cylinders
- Diagnose ignition/fuel injector problems
- Requires engine running

**Implementation:** ~100 lines (highly manufacturer-specific)

### 3.5 Advanced Data Analysis

#### Historical Data Tracking (`obd_save_session`)
Save diagnostic sessions with timestamps:
- Store DTCs, freeze frames, sensor readings
- Track changes over time
- Compare before/after repair

**Implementation:** ~100 lines + database/file storage

#### Session Comparison (`obd_compare_sessions`)
Compare two diagnostic sessions:
- Show new/cleared DTCs
- Sensor value changes
- Monitor status changes
- Generate diff report

**Implementation:** ~80 lines

#### Trend Analysis (`obd_analyze_trends`)
Analyze sensor degradation over multiple sessions:
- O2 sensor response time degradation
- Fuel trim drift
- Catalyst efficiency decline
- Temperature abnormalities

**Implementation:** ~120 lines with statistical analysis

### 3.6 Extended Diagnostic Protocols

#### UDS (Unified Diagnostic Services) Support
**ISO 14229** - Modern diagnostic protocol:
- Used by VAG, BMW, Mercedes (newer models)
- More diagnostic capabilities than OBD-II
- Security/authentication required
- Read/write ECU memory

**Challenges:**
- Requires security seed/key algorithms (often proprietary)
- Legal concerns about ECU modifications
- Bricking risk if misused

**Implementation:** ~500+ lines + security handling

#### KWP2000 Protocol Support
**ISO 14230** - Older diagnostic protocol:
- Used by many European manufacturers
- Pre-CAN vehicles
- Session management
- Security access

**Implementation:** ~400 lines

---

## Phase 4: Convenience & User Experience

These features improve usability and make the tool more accessible.

### 4.1 Guided Diagnostics

#### DTC Troubleshooting Assistant (`obd_diagnose_dtc`)
Provide step-by-step diagnostic guidance:
- Input: DTC code
- Output: Troubleshooting tree with test sequences
- Links to freeze frame data
- Suggests next tests to isolate fault

**Implementation:** ~150 lines + troubleshooting database

#### Repair Verification Workflow (`obd_verify_repair`)
After repair workflow:
1. Clear codes
2. Run specific drive cycle for the fault
3. Monitor for code return
4. Confirm monitors complete
5. Generate verification report

**Implementation:** ~100 lines

#### Drive Cycle Instructions (`obd_get_drive_cycle`)
Provide drive cycle requirements to complete monitors:
- Manufacturer-specific drive patterns
- Speed ranges, duration, idle time needed
- Temperature requirements
- Which monitors will complete with this cycle

**Implementation:** ~80 lines + drive cycle database

### 4.2 Educational Features

#### DTC Explanation (`obd_explain_dtc`)
Plain English explanations:
- What the code means mechanically
- Impact on vehicle operation
- Driving safety implications
- Urgency of repair
- Estimated repair cost range

**Implementation:** ~60 lines + educational content database

#### Sensor Value Interpretation (`obd_interpret_sensor`)
Explain what sensor values mean:
- Normal range for this vehicle/condition
- What high/low values indicate
- Related systems affected
- Diagnostic significance

**Implementation:** ~80 lines

### 4.3 Alert System

#### Smart Alerts (`obd_configure_alerts`)
Configurable alerts for diagnostic conditions:
- Critical DTCs set (flashing MIL)
- Pending codes approaching confirmation
- Mode 06 values approaching limits
- Abnormal sensor readings
- Fuel trim out of range

**Implementation:** ~100 lines

---

## Phase 5: Community & Integration

Features that leverage community knowledge and integrate with other systems.

### 5.1 Community PID Database

#### Community Custom PID Repository
Crowdsourced custom PID definitions:
- Organized by manufacturer/model/year
- User-submitted and verified
- Rating/voting system
- Regular updates

**Implementation:** Requires backend infrastructure + API

#### Submit Custom PID (`obd_submit_custom_pid`)
Allow users to contribute PID definitions:
- Validation before submission
- Community review process
- Attribution to submitter

**Implementation:** ~80 lines + API integration

### 5.2 Integration Features

#### Export to Third-Party Format
Support common diagnostic report formats:
- Alldata format
- Mitchell format
- Generic EOBD format

**Implementation:** ~150 lines per format

#### API Mode
Expose MCP server functionality as REST API:
- Allow web frontends
- Mobile app integration
- Fleet management systems

**Implementation:** ~300 lines + API framework

---

## Implementation Estimates

### Phase 1 (Critical)
- **Estimated effort:** 2-3 weeks
- **Lines of code:** ~800
- **Complexity:** Low-Medium
- **Dependencies:** Mostly uses existing `python-obd` library

### Phase 2 (Professional)
- **Estimated effort:** 4-6 weeks
- **Lines of code:** ~1500
- **Complexity:** Medium
- **Dependencies:** DTC database, Mode 06 understanding

### Phase 3 (Advanced)
- **Estimated effort:** 8-12 weeks
- **Lines of code:** ~2000+
- **Complexity:** High
- **Dependencies:** Extended protocols, manufacturer research

### Phase 4 (UX)
- **Estimated effort:** 4-6 weeks
- **Lines of code:** ~800
- **Complexity:** Medium
- **Dependencies:** Content databases, educational material

### Phase 5 (Community)
- **Estimated effort:** 6-8 weeks
- **Lines of code:** ~1000+
- **Complexity:** High
- **Dependencies:** Backend infrastructure, moderation system

---

## Success Metrics

### Phase 1 Success Criteria
- Can read and clear check engine lights
- Can retrieve freeze frame data
- Can check emission test readiness
- Can query Mercedes transmission fluid temperature (custom PID)
- Replaces basic $50 OBD-II scanner functionality

### Phase 2 Success Criteria
- Can perform comprehensive diagnostics comparable to $200-500 scanner
- Exports professional diagnostic reports
- Tracks Mode 06 data for predictive maintenance

### Phase 3 Success Criteria
- Matches capabilities of $1000+ professional scan tools
- Real-time data logging and analysis
- Multi-module diagnostics

### Phase 4 Success Criteria
- Tool is accessible to DIY mechanics
- Reduces diagnostic time with guided workflows
- Educational value for learning mechanics

### Phase 5 Success Criteria
- Active community contributing PID definitions
- Integration with popular automotive platforms
- Used by professional shops

---

## Notes

### Why No Tests/Examples in Current Codebase?
Current implementation has no test files or usage examples. Recommend adding:
- Unit tests for each tool
- Integration tests with mock OBD connection
- Example usage documentation
- Sample diagnostic scenarios

### Defensive Coding Considerations
Some features (bi-directional control, ECU memory writes) have potential to damage vehicles if misused. Implement:
- Clear warnings before destructive operations
- Confirmation prompts
- Safety timeouts
- Detailed logging of all commands sent

### Legal Considerations
- Some manufacturer-specific protocols are legally protected
- ECU modifications may void warranties
- Emission tampering is illegal in most jurisdictions
- Tool should refuse to disable emission controls

---

## Quick Reference: What Tools Actually Exist vs. What's Needed

### Exists ✅
- `obd_connect`
- `obd_disconnect`
- `obd_status`
- `obd_query_pid`
- `obd_query_multiple`
- `obd_list_supported`
- `obd_engine_data`
- `obd_fuel_system`

### Phase 1 Needed 🚨
- `obd_get_dtcs` (Mode 03)
- `obd_clear_dtcs` (Mode 04)
- `obd_get_pending_dtcs` (Mode 07)
- `obd_get_freeze_frame` (Mode 02)
- `obd_get_readiness` (Mode 01 PID 01)
- `obd_get_mil_status`
- `obd_get_dtc_clear_history`
- `obd_query_custom_pid`

### Phase 2 Needed 📊
- `obd_get_permanent_dtcs` (Mode 0A)
- `obd_get_test_results` (Mode 06)
- `obd_emissions_data`
- `obd_status_data`
- `obd_air_system_data`
- `obd_distance_time_data`
- `obd_export_diagnostic_report`
- `obd_save_custom_pid`
- `obd_query_saved_pid`
- `obd_get_o2_sensors`
- `obd_analyze_fuel_trim`

### Phase 3 Needed ⚡
- `obd_stream_pids`
- `obd_record_on_condition`
- `obd_analyze_catalyst`
- `obd_analyze_evap`
- `obd_scan_all_modules`
- `obd_test_component`
- `obd_cylinder_balance_test`
- `obd_save_session`
- `obd_compare_sessions`
- `obd_analyze_trends`

---

## Recommended Next Steps

1. **Implement Phase 1 DTC tools** - This is the highest priority gap
2. **Add freeze frame support** - Critical for diagnostics
3. **Implement readiness monitors** - Essential for emission testing
4. **Add custom PID support** - Unblocks Mercedes transmission temp use case
5. **Write tests** - Ensure reliability as features grow
6. **Document usage examples** - Help users understand capabilities
7. **Phase 2 features** - Build toward professional-grade tool

This priority list provides a clear roadmap from "partially useful" to "professional-grade diagnostic tool."

---

## ⚠️ Safety Considerations

### Current Implementation: ✅ Completely Safe

All existing features in the codebase are **read-only operations**:
- Connection management
- PID queries (single and batch)
- Category queries (engine, fuel)
- Status checks
- Vehicle metadata retrieval

**No write operations exist.** The current implementation cannot harm the vehicle, erase data, or cause physical danger.

---

### Phase 1 Features: Safety Analysis

#### `obd_clear_dtcs` - ⚠️ MEDIUM RISK

**Dangers:**

1. **Permanent Data Loss**
   - Erases all diagnostic trouble codes permanently
   - Erases freeze frame data (cannot be recovered)
   - Loses valuable troubleshooting information
   - Resets distance/time counters

2. **Emission Testing Failure**
   - Resets all readiness monitors to "not ready"
   - Vehicle will fail emission/smog testing
   - May take 50-100 miles of specific driving to complete monitors
   - Different states allow 1-2 incomplete monitors max

3. **Hidden Problems Lead to Expensive Damage**
   - Clearing P0300 (misfire) without repair → destroyed catalytic converter ($1,000-2,500)
   - Clearing coolant temp codes → warped head/blown gasket ($2,000-4,000)
   - Clearing transmission codes → total transmission failure ($3,000-8,000)
   - Clearing codes does NOT fix problems, only hides them

4. **Legal Issues**
   - Clearing codes to pass emission testing = fraud in most jurisdictions
   - Used car sale without disclosure = consumer fraud
   - Warranty claims after clearing codes = warranty fraud

**Required Safety Measures:**

```python
@mcp.tool()
async def obd_clear_dtcs() -> dict:
    """
    ⚠️  WARNING: DESTRUCTIVE OPERATION ⚠️

    This command will PERMANENTLY:
    - Erase ALL diagnostic trouble codes
    - Erase ALL freeze frame data
    - Reset ALL readiness monitors to "not ready"
    - Turn off check engine light
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

    Requires explicit user confirmation.
    """
```

**Implementation Requirements:**
- Display full warning text
- Require explicit confirmation (not just "yes")
- Log operation with timestamp for accountability
- Consider requiring reason code (e.g., "post-repair", "diagnostic-test")

#### `obd_query_custom_pid` - ⚠️ LOW TO HIGH RISK (Mode-Dependent)

**Safe Modes (Read-Only):**
- `0x01` - Show current data
- `0x02` - Show freeze frame data
- `0x03` - Show stored DTCs
- `0x07` - Show pending DTCs
- `0x09` - Request vehicle information
- `0x0A` - Permanent DTCs
- `0x22` - Read data by identifier (manufacturer-specific reads)

**DANGEROUS MODES (Write Operations) - MUST BE BLOCKED:**
- `0x2E` - Write data by identifier → Can modify ECU memory, **BRICK RISK**
- `0x31` - Routine control → Can activate components, **PHYSICAL DANGER**
- `0x3D` - Write memory by address → **EXTREMELY DANGEROUS**
- `0x3E` - Tester present → Session control, could lock out other tools
- `0x27` - Security access → Unlocks protected functions
- `0x28` - Communication control → Can disable communication
- `0x34`, `0x35`, `0x36`, `0x37` - Memory transfer → **ECU PROGRAMMING**

**Required Safety Measures:**

```python
ALLOWED_READ_MODES = ["01", "02", "03", "07", "09", "0A", "22"]
BLOCKED_WRITE_MODES = ["2E", "31", "3D", "3E", "27", "28", "34", "35", "36", "37"]

@mcp.tool()
async def obd_query_custom_pid(mode: str, pid: str, ...) -> dict:
    """
    Query custom/manufacturer-specific PID.

    SAFETY: Only read-only modes are permitted.
    Write operations are BLOCKED to prevent ECU damage.

    Allowed modes: 01, 02, 03, 07, 09, 0A, 22
    Blocked modes: 2E, 31, 3D, 3E, 27, 28, 34-37
    """
    mode_hex = mode.upper().lstrip("0X")

    if mode_hex in BLOCKED_WRITE_MODES:
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.CUSTOM_COMMAND_ERROR.value,
                message=f"Mode 0x{mode_hex} is a WRITE operation and is blocked for safety",
                suggestion="Use read-only modes: 01, 02, 03, 07, 09, 0A, 22"
            )]
        ).to_dict()

    if mode_hex not in ALLOWED_READ_MODES:
        return OBDResponse(
            ok=False,
            errors=[ErrorInfo(
                type=OBDErrorType.CUSTOM_COMMAND_ERROR.value,
                message=f"Mode 0x{mode_hex} is not in the allowed list",
                suggestion="Use approved read-only modes: 01, 02, 03, 07, 09, 0A, 22"
            )]
        ).to_dict()
```

**Additional Custom PID Risks:**
- Incorrect PID could return unexpected data
- Some ECUs may crash/reset with invalid requests
- Community-sourced PIDs may be wrong or outdated
- Formula errors could display misleading values
- User responsibility to validate PID/formula combinations

#### Other Phase 1 Features: ✅ Safe

All other Phase 1 features are read-only and pose no risk:
- `obd_get_dtcs` - Safe (read-only)
- `obd_get_pending_dtcs` - Safe (read-only)
- `obd_get_freeze_frame` - Safe (read-only)
- `obd_get_readiness` - Safe (read-only)
- `obd_get_mil_status` - Safe (read-only)

---

### Phase 2 Features: Safety Analysis

#### All Phase 2 Features: ✅ Safe

Phase 2 consists entirely of:
- Extended read operations (Mode 06, Mode 0A)
- Data analysis and interpretation
- Export/reporting functions
- Saved PID definitions (local storage only)

**No write operations to vehicle.** All safe.

---

### Phase 3 Features: 🚨 HIGH RISK

Phase 3 includes potentially dangerous features that require extensive safety measures or should not be implemented at all.

#### `obd_test_component` (Bi-Directional Control) - 🚨 HIGH RISK

**Physical Dangers to People:**

1. **Injury from Moving Parts**
   - Cooling fan activation → spinning blades can cause serious injury
   - Throttle actuation → unexpected movement
   - Starter motor while engine running → catastrophic mechanical failure

2. **Fire Risk**
   - Fuel pump activation when dry → pump overheating → fire
   - Commanding overly rich mixture → fuel in exhaust → fire
   - Electrical shorts during testing

3. **Crash Risk**
   - Unexpected engine stall in traffic
   - Disabling cylinders while merging/passing
   - Interference with ABS/stability control
   - Driver distraction from unexpected warnings

4. **Toxic Exposure**
   - EVAP purge activation → gasoline vapor exposure
   - Disabling catalyst → increased CO/NOx exposure

**Mechanical Damage to Vehicle:**

1. **Component Damage**
   - Running fuel pump dry → pump burnout ($300-800)
   - Over-activating solenoids → coil burnout
   - Catalyst tests when cold → thermal shock damage
   - Excessive EVAP testing → fuel bladder damage

2. **Engine Damage**
   - Over-revving via throttle control
   - Wrong fuel injector timing → bent valves
   - Incorrect VGT turbo control → turbo failure ($1,500-3,000)
   - Disabling cylinders incorrectly → mechanical stress

**Required Safety Measures (If Implemented):**

```python
@mcp.tool()
async def obd_test_component(component: str, state: str) -> dict:
    """
    ⚠️⚠️⚠️ ACTIVE TEST - ACTIVATES PHYSICAL COMPONENTS ⚠️⚠️⚠️

    DANGER - This command can:
    - Activate cooling fans (INJURY RISK - spinning blades)
    - Run fuel pump (FIRE RISK if dry)
    - Operate solenoids and relays
    - Affect engine operation

    SAFETY REQUIREMENTS:
    ✓ Engine must be running (for most tests)
    ✓ Vehicle must be in PARK/NEUTRAL
    ✓ Parking brake must be engaged
    ✓ Keep hands/tools clear of engine bay
    ✓ Maximum activation time: 30 seconds (automatic timeout)
    ✓ Never run tests while driving
    ✓ Ensure adequate ventilation (garage door open)

    WARNINGS:
    - Some tests illuminate check engine light temporarily
    - Test results do not guarantee component is good
    - Professional training recommended
    """

    # Safety checks
    rpm_response = connection.query(obd.commands.RPM)
    if not rpm_response or rpm_response.is_null():
        return error("Cannot read engine RPM - unsafe to proceed")

    rpm = rpm_response.value.magnitude
    if rpm < 500:
        return error("Engine must be running for active tests")

    speed_response = connection.query(obd.commands.SPEED)
    if speed_response and not speed_response.is_null():
        speed = speed_response.value.magnitude
        if speed > 0:
            return error("Vehicle must be stationary (PARK/NEUTRAL) for active tests")

    # Maximum activation time
    MAX_ACTIVATION_TIME = 30  # seconds

    # Accountability logging
    logger.warning(f"ACTIVE TEST STARTED: {component} → {state} | User: {user_id} | Timestamp: {timestamp}")

    # ... perform test with timeout ...

    logger.warning(f"ACTIVE TEST COMPLETED: {component}")
```

**Recommendation:** Consider not implementing bi-directional control at all. Risk-to-benefit ratio is poor for a general-purpose tool.

#### Extended Diagnostic Protocols (UDS/KWP2000) - 🚨 CRITICAL RISK

**DO NOT IMPLEMENT ECU Programming Features**

UDS (Mode 0x34-0x37) and similar protocols enable:

**Extremely Dangerous Capabilities:**
- **ECU Flashing/Reprogramming** → Brick ECU if power loss ($500-3,000 dealer replacement)
- **Memory Writes** → Corrupt ECU software
- **Security Bypass** → Disable immobilizer (theft enablement)
- **Calibration Changes** → Engine damage, emission violations

**Illegal Operations:**
- **VIN Modification** → Felony in all US states
- **Odometer Reset** → Federal crime, up to 3 years prison
- **Emission Defeat** → Federal Clean Air Act violation, up to $3,750/day fine
- **Immobilizer Defeat** → Enables vehicle theft

**Legal Liability:**
- Providing tools that enable crimes
- Facilitating warranty fraud
- Enabling emission tampering
- Vehicle theft enablement

**Recommendation:** **DO NOT IMPLEMENT.** The legal, ethical, and safety risks far outweigh any legitimate diagnostic benefit.

**Alternative:** If advanced diagnostics are needed, stick to read-only UDS modes (0x22 - Read Data By ID) and explicitly block all write/programming modes.

#### Other Phase 3 Concerns

**`obd_stream_pids` - ⚠️ MODERATE RISK**
- Risk: Driver distraction if used while driving
- Mitigation: Clear warnings against use while driving
- Otherwise safe (read-only)

**`obd_scan_all_modules` - ✅ SAFE**
- Read-only operation
- May trigger warning lights temporarily (normal diagnostic behavior)

---

### Legal Dangers ⚖️

#### US Federal Clean Air Act

**Prohibits:**
- Tampering with emission control systems
- Defeating emission monitors
- Modifying calibration to increase performance
- Clearing codes to fraudulently pass inspection
- Selling/distributing defeat devices

**Penalties:**
- Civil: Up to $3,750 per violation (per vehicle, per day)
- Criminal: Felony charges for knowing violations
- EPA enforcement actions

**Examples of Violations:**
- Clearing codes to pass smog check without repair
- Disabling readiness monitors
- Tuning ECU to bypass catalyst efficiency monitoring
- Providing software that automates these actions

#### Odometer Fraud (Federal Law)

**49 USC §32703 - Altering Odometers**

**Prohibits:**
- Disconnecting, resetting, or altering odometer
- Conspiracy to alter odometer
- Advertising services to alter odometer

**Penalties:**
- Criminal: Up to 3 years imprisonment
- Civil: $10,000 fine per violation
- Private lawsuits: Treble damages

**OBD-II Connection:**
- Modern vehicles store odometer in ECU
- Some diagnostic protocols can modify stored mileage
- Even reading for legitimate purposes creates legal exposure

#### State Laws

**Vary by state, commonly prohibit:**
- Unauthorized VIN modification
- Defeating safety systems (airbags, ABS)
- Inspection fraud
- Consumer protection violations (hiding defects)

#### Warranty Implications

**Magnuson-Moss Warranty Act Considerations:**
- Manufacturers may void warranty for improper diagnostic tool use
- Clearing codes to hide abuse before warranty claim = fraud
- Using non-approved tools may give manufacturer grounds to deny claims

**Disclaimer Requirement:** Tool should include clear statement that improper use may void warranty.

---

### Physical Safety Best Practices

#### For Users

**Before Using Tool:**
1. ✓ Park on level surface
2. ✓ Engage parking brake
3. ✓ Shift to PARK (automatic) or NEUTRAL (manual)
4. ✓ Ensure adequate ventilation
5. ✓ Keep hands/tools away from moving parts
6. ✓ Never use diagnostic features while driving

**Read Operations (Always Safe):**
- Query PIDs
- Read DTCs
- Check readiness monitors
- Export diagnostic reports

**Write Operations (Require Caution):**
- Clear DTCs → Save data first, understand consequences
- Custom PIDs → Only use verified read-only modes

**NEVER Attempt:**
- ECU programming/flashing
- Memory writes
- VIN modification
- Odometer changes
- Active tests while driving

#### For Developers

**Defensive Coding:**
1. **Whitelist, Don't Blacklist**
   - Explicitly allow safe modes
   - Reject unknown modes by default
   - Don't rely on blacklist (may miss new dangerous modes)

2. **Fail Safe**
   - Default to read-only
   - Require explicit opt-in for any write operation
   - Timeout all active tests

3. **Logging & Accountability**
   - Log all write operations
   - Include timestamps and user identifiers
   - Create audit trail

4. **Input Validation**
   - Validate all hex codes
   - Check formula syntax before execution
   - Sanitize user inputs

5. **User Warnings**
   - Clear, prominent warnings
   - Explain consequences in plain language
   - Require acknowledgment, not just "OK"

**Code Example - Safe Mode Validation:**
```python
def validate_mode_safety(mode: str) -> tuple[bool, str]:
    """
    Validate that diagnostic mode is safe (read-only).

    Returns:
        (is_safe, explanation)
    """
    READ_ONLY_MODES = {
        "01": "Show current data",
        "02": "Show freeze frame data",
        "03": "Show stored DTCs",
        "07": "Show pending DTCs",
        "09": "Request vehicle information",
        "0A": "Permanent DTCs",
        "22": "Read data by identifier"
    }

    mode_clean = mode.upper().lstrip("0X").zfill(2)

    if mode_clean in READ_ONLY_MODES:
        return True, READ_ONLY_MODES[mode_clean]

    # Known dangerous modes
    if mode_clean in ["2E", "31", "3D", "3E", "27", "28", "34", "35", "36", "37"]:
        return False, f"Mode 0x{mode_clean} is a WRITE operation and is blocked for safety"

    # Unknown mode - reject by default (fail safe)
    return False, f"Mode 0x{mode_clean} is not in the approved read-only mode list"
```

---

### Documentation Requirements

#### README.md Must Include Safety Section

**Proposed Safety Documentation:**

```markdown
## ⚠️ Safety & Legal Warnings

### Safe Operations
All PID queries, status checks, and diagnostic data reads are **completely safe** and cannot harm your vehicle.

### Operations Requiring Caution

#### Clearing Diagnostic Trouble Codes
**IMPORTANT:** Clearing DTCs does NOT fix problems, it only erases diagnostic history.

**Before clearing codes:**
- ✓ Save/document all DTCs and freeze frames
- ✓ Complete repairs to address root cause
- ✓ Understand your vehicle will fail emission testing until monitors complete
- ✓ Be prepared to drive 50-100 miles for monitors to complete

**Never clear codes to:**
- ✗ Pass emission/smog testing without fixing problem (illegal)
- ✗ Hide defects before selling vehicle (fraud)
- ✗ Conceal problems before warranty claim (fraud)

**Potential Consequences:**
- Unrepaired misfires can destroy catalytic converter ($1,000-2,500 repair)
- Hidden problems can escalate to major failures
- Legal penalties for fraud or emission tampering

#### Custom PIDs
This tool allows querying manufacturer-specific PIDs for advanced diagnostics.

**Safety:** Only read-only modes are permitted. Write modes are blocked.

**User Responsibility:**
- Verify PID codes from reliable sources
- Test formulas with known values before trusting
- Understand that incorrect PIDs may return garbage data
- Community PIDs may be outdated or vehicle-specific

### Legal Notices

#### Emission Tampering (Federal Crime)
The US Clean Air Act prohibits:
- Tampering with emission controls
- Defeating emission monitors
- Clearing codes to pass testing fraudulently

**Penalties:** Up to $3,750 per violation (per vehicle, per day)

#### Odometer Fraud (Federal Crime)
Federal law prohibits modifying odometer readings stored in vehicle ECUs.

**Penalties:** Up to 3 years imprisonment + $10,000 fine per violation

#### Warranty
Improper diagnostic tool use may void manufacturer warranty. Use at your own risk.

#### Disclaimer
This tool is provided for legitimate diagnostic purposes only. Users are solely responsible for:
- Compliance with all applicable laws
- Proper use of diagnostic features
- Any damage resulting from misuse
- Vehicle safety during diagnostic operations

**This tool does not enable and explicitly blocks:**
- ECU reprogramming/flashing
- VIN modification
- Odometer changes
- Emission system defeats
- Security system bypasses

### Best Practices

**DO:**
- ✓ Read and save DTCs before clearing
- ✓ Save freeze frame data for records
- ✓ Fix problems before clearing codes
- ✓ Use for legitimate diagnostics and repairs
- ✓ Keep vehicle stationary during diagnostics
- ✓ Ensure adequate ventilation

**DON'T:**
- ✗ Clear codes to hide problems
- ✗ Use while driving
- ✗ Attempt to modify ECU settings
- ✗ Use write modes in custom PIDs
- ✗ Tamper with emission systems
- ✗ Violate applicable laws

**When in Doubt:**
Consult a qualified mechanic or vehicle manufacturer documentation.
```

---

### Liability Considerations

#### For Open Source Distribution

**Recommended License Additions:**

```
ADDITIONAL DISCLAIMERS:

VEHICLE SAFETY: This software interfaces with vehicle safety-critical systems.
Improper use can result in vehicle damage, personal injury, or death. Users
assume all responsibility for safe operation.

NO WARRANTY: This software is provided "AS IS" without warranty of any kind.
The authors assume no liability for vehicle damage, personal injury, property
damage, or legal consequences resulting from use of this software.

COMPLIANCE: Users are solely responsible for compliance with all applicable
laws including but not limited to emission regulations, odometer tampering
laws, warranty terms, and consumer protection laws.

PROFESSIONAL USE: This tool is not a substitute for professional diagnostic
equipment or qualified mechanic expertise. Critical repairs should be performed
by qualified professionals.
```

#### For Commercial Use

If distributed commercially:
- **General Liability Insurance** - Cover vehicle damage claims
- **Professional Liability Insurance** - Cover diagnostic errors
- **Product Liability Insurance** - Cover safety incidents
- **Legal Review** - Ensure compliance with all regulations
- **Terms of Service** - Clear liability limitations
- **User Agreement** - Explicit acknowledgment of risks

---

### Summary: Safety Implementation Checklist

#### Phase 1 Implementation (Immediate)

- [ ] Implement mode validation for `obd_query_custom_pid`
  - [ ] Whitelist read-only modes (01, 02, 03, 07, 09, 0A, 22)
  - [ ] Block write modes (2E, 31, 3D, 3E, 27, 28, 34-37)
  - [ ] Reject unknown modes by default

- [ ] Add comprehensive warnings to `obd_clear_dtcs`
  - [ ] Explain data loss consequences
  - [ ] Warn about emission testing failure
  - [ ] Explain potential damage from unrepaired issues
  - [ ] Require explicit confirmation
  - [ ] Log all clear operations

- [ ] Update README.md with safety section
  - [ ] Document safe vs. dangerous operations
  - [ ] Include legal warnings
  - [ ] Provide best practices
  - [ ] Add liability disclaimers

- [ ] Add logging for accountability
  - [ ] Log all clear DTC operations
  - [ ] Log custom PID queries
  - [ ] Include timestamps

#### Phase 2 Considerations

- [ ] All Phase 2 features are read-only - no safety concerns
- [ ] Consider adding educational warnings about interpreting Mode 06 data

#### Phase 3 Decisions (Before Implementation)

- [ ] **DECISION:** Implement bi-directional control?
  - If YES:
    - [ ] Implement extensive safety checks
    - [ ] Add vehicle state validation
    - [ ] Implement automatic timeouts
    - [ ] Add accountability logging
    - [ ] Test extensively with mock hardware
  - Recommendation: **NO** - risk outweighs benefit

- [ ] **DECISION:** Implement extended protocols (UDS/KWP2000)?
  - If YES (read-only modes ONLY):
    - [ ] Explicitly block programming modes
    - [ ] Whitelist approved read modes only
    - [ ] Add extra legal disclaimers
  - Recommendation: **MAYBE** - only read modes, heavy restrictions

- [ ] **DECISION:** Implement ECU programming?
  - Recommendation: **ABSOLUTELY NOT** - critical safety/legal risk

#### Ongoing

- [ ] Monitor for misuse reports
- [ ] Update documentation based on user feedback
- [ ] Review safety measures as new features added
- [ ] Stay informed about regulatory changes
- [ ] Consider liability insurance for distribution

---

## Final Safety Statement

**Current Implementation (Phase 0):** Completely safe - all read-only operations.

**Phase 1 with Safety Measures:** Safe for responsible users with proper warnings and restrictions in place.

**Phase 3 Advanced Features:** High risk - require extensive safety engineering or should not be implemented.

**Never Implement:** ECU programming, VIN modification, odometer changes, emission defeats.

The key principle: **Default to read-only. Require explicit, informed consent for any write operation. Block dangerous operations entirely.**
