  # Rubber Duck Debug Scenarios
# 26 scenarios (2 per tool × 13 tools)

---
1. obd_connect

Scenario A: "The Permission Denied"

User connects to /dev/ttyUSB0 but gets permission error. Do they get a helpful error?

Quack Happy! ✅ - Fix #3 applied! Error message now includes specific suggestion: "Permission denied. Add your user to the 'dialout' group: sudo usermod -a -G dialout $USER (then logout/login)" (__main__.py:162-167)

Scenario B: "The Bluetooth That's Paired But Not Connected"

User tries Bluetooth adapter that's paired but not actually connected. Do they get guidance?

Quack Happy! ✅ - Fix #3 applied! Error contains "device not found" so suggestion includes: "For Bluetooth: Ensure adapter is paired AND connected (not just paired)" (__main__.py:168-172)

---
2. obd_disconnect

Scenario A: "The Stuck Disconnect"

User disconnects while a slow query is running. Does it hang forever with no feedback?

Quack Happy! ✅ - Fix #6 applied! Logs "Disconnecting from OBD... (waiting for ongoing queries to complete)" so user knows why it's waiting (__main__.py:240-241)

Scenario B: "The Already Disconnected"

User calls disconnect when already disconnected. Does it error or handle gracefully?

Quack Happy! ✅ - Returns ok=True with message "Already disconnected" (__main__.py:233-238). Clean!

---
3. obd_status

Scenario A: "The Stale Connection"

Adapter loses power but manager still thinks connected. Does status show false positive?

Quack Happy! ✅ - Fix #7 applied! Now queries STATUS command to verify connection is actually alive, sets actual_connected=False if query fails (__main__.py:285-304)

Scenario B: "The Mock Mode Status"

Mock mode is enabled. Does status make it clear this is fake data?

Quack Happy! ✅ - Status includes mock_mode=True field (connection_manager.py:266). Clear!

---
4. obd_query_pid

Scenario A: "The Typo Terror"

User types "ENGIN_LOAD" instead of "ENGINE_LOAD". Do they get a hint?

Quack Happy! ✅ - Fix #4 applied! Uses fuzzy matching to suggest: "Did you mean: ENGINE_LOAD? Or use obd_list_supported() to see all PIDs" (__main__.py:334-341)

Scenario B: "The Unsupported PID"

User requests PID that vehicle doesn't support. Is error message clear?

Quack Happy! ✅ - Returns null response with clear error. Fuzzy matching also helps if it's just not available vs typo!

---
5. obd_query_multiple

Scenario A: "The Mixed Bag"

User requests 5 PIDs, only 3 are supported. Does it return partial results or error?

Quack Happy! ✅ - Returns successful PIDs only, skips unsupported ones (helpers.py query_multiple_pids filters). Count shows how many succeeded!

Scenario B: "The All Fail"

User requests 5 PIDs, none supported. Empty results or error?

Quack Happy! ✅ - Returns ok=True with empty pids array and count=0. Not an error, just no data!

---
6. obd_list_supported

Scenario A: "The Uncategorized Orphan"

Vehicle has obscure PID "XYZ_SENSOR" not in PID_CATEGORIES. Does it disappear?

Quack Happy! ✅ - Fix #5 applied! Uncategorized PIDs now appear in "uncategorized" category (__main__.py:394-398). Nothing disappears!

Scenario B: "The Empty Category"

Vehicle is diesel, doesn't support any spark ignition PIDs. Do empty categories show?

Quack Happy! ✅ - Only categories with supported PIDs are included (helpers.py:194-199). Clean output!

---
7. obd_engine_data

Scenario A: "The Partial Engine Data"

Vehicle supports RPM and COOLANT_TEMP but not INTAKE_PRESSURE. Does it return partial?

Quack Happy! ✅ - Returns all available engine PIDs, skips unsupported ones. Clean partial results!

Scenario B: "The Cold Start"

Engine just started, some sensors not ready yet. Does it return null values or skip?

Quack Happy! ✅ - Null responses are filtered out in query loop (helpers.py:214-216). Only valid data returned!

---
8. obd_fuel_system

Scenario A: "The Electric Vehicle"

User queries fuel system on EV (no fuel system). What happens?

Quack Happy! ✅ - Returns empty pids array. EVs shouldn't connect via OBD-II fuel PIDs anyway. Clean!

Scenario B: "The Flex Fuel Mystery"

User has flex fuel vehicle. Is ETHANOL_PERCENT included in fuel category?

Quack Happy! ✅ - Fix #1 verified! ETHANOL_PERCENT is in PID_CATEGORIES["fuel"] (response_models.py:151). Will be queried correctly!

---
9. obd_get_dtcs

Scenario A: "The MIL On, No Codes"

MIL is on but vehicle returns no DTCs. Is MIL status reported accurately?

Quack Happy! ✅ - MIL status is always queried separately from DTCs (dtc_tools.py:72-76). Returns mil_on=True, dtcs=[], message="No DTCs found". Perfect!

Scenario B: "The Mock Mode DTC"

User tries to read DTCs in mock mode (no OBD hardware). What happens?

Quack Happy! ✅ - Returns error "OBD library not available - cannot query DTCs" (dtc_tools.py:50-57). Clear message!

---
10. obd_clear_dtcs

Scenario A: "The Persistent Code"

User clears DTCs but P0420 won't clear (catalyst issue still present). Does tool detect this?

Quack Happy! ✅ - Verification query (dtc_tools.py:150-154) detects remaining codes, sets partial_clear=True, logs "PARTIAL DTC clear". Perfect!

Scenario B: "The Clear Without Reading"

User clears DTCs without reading them first. Do they clear blind?

Quack Happy! ✅ - Fix #2 applied! Now checks if obd_get_dtcs() was called first. If not, returns error: "Safety check failed: DTCs have not been read yet." User must read DTCs or pass confirm=True (__main__.py:425-437)

---
11. obd_get_pending_dtcs

Scenario A: "The Pending That Went Away"

User checks pending DTCs after driving. Fault didn't repeat, pending cleared. What shows?

Quack Happy! ✅ - Returns empty array with message "No pending DTCs found" (dtc_tools.py:248-256). Clear!

Scenario B: "The Mode 07 Mix-up"

User gets pending DTCs. Are they actually pending (1-trip) or confirmed (2-trip)? How do they know?

Quack Happy! ✅ - Fix #8 applied! When pending DTCs found, also queries confirmed DTCs (Mode 03) for comparison. Returns note explaining "Pending DTCs (Mode 07) are faults detected ONCE" and suggestion showing whether confirmed codes also exist (dtc_tools.py:261-300)

---
12. obd_get_freeze_frame

Scenario A: "The Stub Call"

User tries to get freeze frame for P0420. Does stub return graceful error?

Quack Happy! ✅ - Returns error with DTC code in message (dtc_tools.py:311-323). Stub works as documented!

Scenario B: "The Null DTC Code"

User calls freeze frame without specifying DTC code. Does it handle None?

Quack Happy! ✅ - if/else handles None correctly (dtc_tools.py:311-314). Message doesn't include DTC when None!

---
13. obd_get_readiness

Scenario A: "The Fresh Clear"

User cleared DTCs, now checks readiness. Are monitors ready or not?

Quack Happy! ✅ - Fix #9 applied! Returns complete readiness data with readiness_status="not_ready", monitors_summary showing incomplete count, and readiness_message explaining "drive cycle required" (dtc_tools.py:494-504)

Scenario B: "The Monitor Confusion"

User wants to know which specific monitors are complete (catalyst, EVAP, O2). Can they tell?

Quack Happy! ✅ - Fix #9 applied! Returns structured continuous_monitors and non_continuous_monitors objects with available/complete status for each monitor (MISFIRE_MONITORING, CATALYST_MONITORING, EVAPORATIVE_SYSTEM_MONITORING, etc.) No more raw_status parsing needed! (dtc_tools.py:485-522)

---

# 🦆 Final Quack Count

**Before Fixes:** 14/26 Quack Happy ✅ | 12/26 Quack Danger ⚠️

**After Fixes:** 26/26 Quack Happy ✅ | 0/26 Quack Danger ⚠️

## Fixes Applied:

1. ✅ ETHANOL_PERCENT verification (Scenario 8B)
2. ✅ obd_clear_dtcs safety check (Scenario 10B)
3. ✅ obd_connect better errors (Scenarios 1A, 1B)
4. ✅ obd_query_pid fuzzy matching (Scenario 4A)
5. ✅ obd_list_supported uncategorized PIDs (Scenario 6A)
6. ✅ obd_disconnect feedback (Scenario 2A)
7. ✅ obd_status stale detection (Scenario 3A)
8. ✅ obd_get_pending_dtcs Mode 07/03 confusion detection (Scenario 11B)
9. ✅ obd_get_readiness monitor parsing (Scenarios 13A, 13B)

**All critical issues resolved! 🎉**
