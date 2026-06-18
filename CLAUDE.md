# CLAUDE.md - PLC Test Suite Developer Guide

This document captures the project's goals, architecture, decisions, and known issues for future development.

## Project Goal

Create a GUI-based testing and simulation tool that allows control engineers to automate PlantPAx equipment testing without writing temporary ladder logic. Instead, users write Python simulation modules that can be saved, shared, and reused.

**Core value proposition:**
- Replace tedious manual tag writes with automated simulation logic
- Enable rapid testing before field installation
- Provide interactive controls for fault injection testing
- Give PLC engineers a modern, intuitive testing interface

## Stack

### Runtime
- **Python:** 3.8+ (3.11+ recommended)
- **GUI Framework:** PyQt6 (6.4.0+)
- **Code Editor:** QScintilla (PyQt6-QScintilla 2.14+) for the script editors
- **Code Intelligence:** jedi (0.19+) for hover help / signatures
- **PLC Communication:** pycomm3 (1.2.0+)
- **File Format:** JSON (for .simmod modules)

### Build & Distribution
- **Executable:** PyInstaller (one-file mode)
- **Installer:** Inno Setup (optional, for professional distribution)
- **Version Control:** Git/GitHub
- **CI/CD:** GitHub Actions (coming soon)

### Documentation
- **README:** Standard GitHub markdown
- **Wiki:** GitHub Wiki pages (per-tab guides + examples)
- **Code Comments:** Inline where logic is non-obvious
- **Type Hints:** Used in module data classes, optional elsewhere

## Conventions

### Versioning
Format: `MAJOR.YY.MM.MINOR`
- **MAJOR:** Breaking changes, major features (increment manually)
- **YY:** Release year (auto: current year)
- **MM:** Release month (auto: current month)
- **MINOR:** Incremental releases within month (reset to 01 each month)

Example: `1.26.02.01` = Major v1, February 2026, first release

### Naming
- **Classes:** `PascalCase` (e.g., `SimEngine`, `ModuleEditorWidget`)
- **Functions:** `snake_case` (e.g., `read_tags`, `_on_item_expanded`)
- **Variables:** `snake_case` (e.g., `tag_name`, `flow_rate`)
- **Private methods:** prefix with `_` (e.g., `_start_heartbeat`)
- **Constants:** `UPPER_SNAKE_CASE` (rare in this project)

### Tag Aliases
- No dots: ✅ `valve_cmd` not `valve.cmd`
- No spaces: ✅ `tank_level` not `tank level`
- Descriptive: ✅ `flow_rate` not `f` or `fr`
- Short enough: ✅ `tank_level` not `current_tank_water_level_in_gallons`

### File Organization
```
plc-test-suite/
├── plc_test_suite/           # Main package
│   ├── __init__.py           # Version string
│   ├── main.py               # Main GUI application
│   ├── plc_connection.py     # PLC communication wrapper
│   ├── sim_module.py         # SimModule data model + SimEngine
│   ├── sim_tab.py            # Simulation UI components
│   ├── trend_tab.py          # Live trend plotting (pyqtgraph)
│   ├── tag_browser.py        # Tag discovery UI
│   ├── user_inputs.py        # Interactive control widgets
│   └── syntax_highlighter.py # Python code syntax highlighting
├── tests/                    # Test cases (empty, future use)
├── examples/                 # Example .simmod files
├── pyproject.toml            # Package metadata
├── README.md                 # User-facing documentation
└── CLAUDE.md                 # This file
```

### Module File Format (.simmod)
JSON structure:
```json
{
  "name": "Module Name",
  "description": "What this tests",
  "sim_tags": ["Tag1.cfg_sim", "Tag2.cfg_sim"],
  "input_tags": [
    {"tag": "FullTagName.command", "alias": "my_var"}
  ],
  "output_tags": [
    {"tag": "FullTagName.inp_sim", "alias": "my_output"}
  ],
  "user_inputs": [
    {
      "alias": "manual_override",
      "input_type": "float",
      "label": "Manual Override",
      "default_value": 0.0,
      "min_val": null,
      "max_val": null
    }
  ],
  "init_script": "# One-time setup\ntank_level = 0.0\n",
  "loop_script": "# Runs every interval\ntank_level += 1.0\n",
  "interval_seconds": 1.0
}
```

## Architecture Decisions

### 1. Separation of Data Model from Engine

**Decision:** `SimModule` (data) and `SimEngine` (execution) are separate classes

**Why:**
- Data can be serialized independently (save/load .simmod files)
- Engine logic stays pure Python execution
- UI (ModuleEditorWidget) works with SimModule, not engine
- Makes testing easier (in future)

**Trade-off:** Small amount of boilerplate connecting them

### 2. Background Threads for Long Operations

**Decision:** Tag loading and UDT expansion run in background threads (QThread)

**Why:**
- UI remains responsive during 10-30 second tag load
- Users see progress dialog instead of frozen window
- Essential for good UX with large PLC programs

**Gotcha:** Must store thread references to prevent garbage collection during execution

### 3. SimEngine Runs in Main GUI Thread

**Decision:** `SimEngine._loop()` runs in daemon thread, NOT main thread

**Why:**
- Prevents blocking the GUI during simulation
- Allows user to adjust inputs while simulating
- UI events (buttons, sliders) remain responsive

**Trade-off:** Must use thread-safe mechanisms (Qt signals, locks if modifying shared state)

### 4. User Inputs Injected via Callback

**Decision:** SimEngine doesn't know about UI; instead takes a callback for user input values

```python
def set_user_input_callback(self, callback):
    self._user_input_callback = callback
```

**Why:**
- Engine stays decoupled from UI
- Same engine could run headless, CLI, or different UI
- Clean separation of concerns

**Implementation:** In `_loop()`, calls callback and injects returned dict into script namespace

### 5. Tag Aliases Required (No Direct Tag References)

**Decision:** Scripts use aliases (`tank_level`), not full tag names (`Tank.inp_sim`)

**Why:**
- Avoids Python syntax error with dots in variable names
- Makes scripts readable and refactorable
- Users can change tag names without updating scripts
- Reduces typos

**Trade-off:** Small extra configuration step, but worth it

### 6. Single-Tag Read/Write Bug Handling

**Decision:** Check if result is list; if not, wrap in list

```python
results = self.plc.read(*tag_names)
if not isinstance(results, list):
    results = [results]
```

**Why:** pycomm3 returns single object (not list) when reading one tag. This quirk is now handled transparently

**Gotcha:** Could be hiding similar issues in write operations - monitor this

### 7. Graceful PLC Disconnect Failure

**Decision:** Catch all exceptions during `plc.close()`, log as warning

**Why:** Connection may already be broken (network cable, PLC power, etc.). Don't crash on disconnect

```python
try:
    self.plc.close()
except Exception as e:
    logger.warning(f"Error during disconnect: {e}")
finally:
    self.connected = False
```

**Trade-off:** Silent failures make debugging harder, but prevents frustration on normal shutdown

### 8. UDT Expansion Separate from Tag List

**Decision:** Tag list loaded once; UDT expansion happens on-demand when user clicks ►

**Why:**
- Initial load is fast (all tags, no member details)
- Saves bandwidth for complex structures
- User only expands what they need to see

**Trade-off:** Two network operations instead of one; slightly slower UX but better scalability

### 9. Collapsible Execution Log

**Decision:** Log can be hidden to give more space to editor

**Why:**
- Script editors are the main workspace
- Log only needed when debugging
- Users prefer compact UI during active work

**Implementation:** Simple button toggle, not state-persistent

### 10. Public Repository

**Decision:** Code is public on GitHub; users can fork/contribute

**Why:**
- No proprietary information (generic tool, not company IP)
- Community can benefit
- Open-source model fits well
- Easier distribution via GitHub Releases

**Trade-off:** Someone could use without contributing back, but culture is collaborative

## What's Implemented ✅

### Core Features
- [x] Tag Monitor tab (real-time multi-tag viewing)
- [x] Quick Write tab (manual tag writes with type detection)
- [x] Simulation Modules (full Python scripting engine)
- [x] Tag Browser with UDT expansion
- [x] User Input Controls (float, int, momentary, toggle)
- [x] Module save/load (.simmod JSON files)
- [x] QScintilla script editor: syntax highlighting, line numbers, auto-indent,
      brace matching, bracket auto-close
- [x] Alias-aware autocomplete (tag/user-input aliases + keywords + builtins +
      whitelisted modules), Jedi hover help/signatures
- [x] Compile-only syntax checking (live error markers + pre-run gate before PLC writes)
- [x] Whitelisted `math` / `time` / `random` available in scripts
- [x] Scripts can end the simulation gracefully via `stop("reason")` (disables sim
      tags and resets the UI, same as the Stop button)
- [x] Trend tab: live pyqtgraph plot of input/output/user-input aliases, per-channel
      color, samples logged each sim cycle, persists after stop, save/load reloadable CSV
- [x] Run All / Run Single: a Run Controls checkbox runs every module concurrently
      (multiple engines) or just the selected one; trend channels are module-prefixed
      when several run; Stop stops all, script `stop()` ends one and keeps the rest
- [x] Active-simulation indicator in the persistent PLC connection box (module name /
      "All Modules" / None) so the running module is visible from any tab
- [x] Collapsible execution log
- [x] Optional heartbeat tag for connection status
- [x] Error handling (graceful disconnect, protected UDTs)

### Testing & Validation
- [x] Multiple tab integration
- [x] Real PLC testing (tested with actual CompactLogix)
- [x] Large tag lists (631+ tags)
- [x] PlantPAx-specific features (simulation tags, UDTs)

### Documentation
- [x] Comprehensive README
- [x] 5 wiki pages (per-tab guides)
- [x] Installation guide
- [x] Quick start tutorial
- [x] This CLAUDE.md

### Distribution
- [x] GitHub package distribution via pip
- [x] PyInstaller standalone executable
- [x] Semantic versioning (MAJOR.YY.MM.MINOR)
- [x] GitHub Releases setup

## What's Next 🔮

### Current State (June 2026, v1.26.06.03)
The script editor is now the standout feature: a QScintilla-based mini-IDE with
alias-aware autocomplete, Jedi hover help, compile-only syntax checking (live +
pre-run gate), packaged `math`/`time`/`random`, and a `stop()` function so scripts
can end a run gracefully. Three releases shipped this cycle (`.01` version
reconciliation, `.02` editor upgrade, `.03` script `stop()`), all published to GitHub
Releases with the standalone exe. The app builds clean from source and frozen.

Nothing below is started — these are the open ideas, roughly prioritized.

### Short Term (Next 1-2 releases)
- [ ] GitHub Actions for automated .exe builds (still fully manual via PyInstaller)
- [ ] Code signing for .exe (eliminates the Windows SmartScreen warning — gotcha #6)
- [ ] Example modules for common scenarios (tank fill, PID loop, fault injection)
- [ ] User preferences (default IP, favorite modules, theme)

### Code cleanup (low effort, surfaced during the editor work)
- [ ] Delete unused `syntax_highlighter.py` / `PythonHighlighter` (QScintilla replaced it)
- [ ] Remove the duplicate `_add_user_input` definition in `ModuleEditorWidget`
- [ ] Optional: let Jedi drive context completion (dotted attrs) too — today Jedi
      powers hover only; autocomplete is QsciAPIs (aliases/keywords/builtins/module members)
- [ ] Manual check still pending: confirm `math.sqrt` hover works in the *frozen* exe
      (verified from source; jedi/typeshed data is bundled)

### Medium Term
- [ ] Historical data logging (record tag values over time)
- [ ] Data visualization (plot tag history)
- [ ] Test result export (CSV/Excel)
- [ ] Module templates (wizard for common patterns)
- [ ] Network simulation (add artificial latency/dropout)

### Long Term
- [ ] Multi-PLC support (switch between PLCs mid-session)
- [ ] Visual device relationship diagrams
- [ ] Batch operations (enable sim for all valves in area)
- [ ] Recipe/sequence recording (record actual PLC operation, replay as simulation)
- [ ] Mobile/web interface (for HMI integration)
- [ ] Collaborative testing (multiple users on same simulation)

## Known Gotchas ⚠️

### 1. User Inputs Not Auto-Persisted in collect_module()
**Issue:** User inputs are stored in `self._module` during editing, but `collect_module()` doesn't automatically grab them

**Why:** By design - avoids overwriting user inputs with stale data

**Solution:** Access user inputs from loaded module: `self._module.user_inputs if self._module else []`

**Lesson:** State management across UI components requires careful tracking

### 2. Script Namespace Persists Between Loops
**Feature:** Variables created in one loop iteration exist in next iteration
```python
if 'counter' not in dir():
    counter = 0
counter += 1
```

**Good for:** State tracking, timers, history
**Bad for:** Can confuse users who expect fresh namespace each loop

**Mitigation:** Document this clearly in scripting guide

### 3. pycomm3 Single-Tag Return Type Inconsistency
**Issue:** `read()` returns list when >1 tag, single object when 1 tag

**Our fix:** Check `isinstance(results, list)` and wrap if needed

**Risk:** Other methods might have similar quirks we haven't discovered

**Mitigation:** Test with various tag counts; add similar checks if issues appear

### 4. Tag Aliases With Spaces or Dots Fail Silently
**Issue:** User enters "tag name" as alias → `exec()` treats as syntax error but doesn't crash

**Current behavior:** Script error in log, execution stops

**Better:** Validate aliases when added (no dots, spaces, special chars)

**To fix:** Add validation in `_add_user_input()` and output tag UI

### 5. Protected UDT Structures (AOIs)
**Issue:** Add-On Instructions have protected internals, can't expand

**Current:** Shows "Protected structure (AOI)" - informative but not expandable

**Limitation:** User can't browse AOI members; must know names from documentation

**Acceptable because:** AOIs are less common, documentation available

### 6. Windows Defender Flags Unsigned Executables
**Issue:** First-time users see "Windows protected your PC" warning

**Current workaround:** Tell users to click "More info" → "Run anyway"

**Better solution:** Code signing certificate ($200-500/year)

**Decision:** Not worth it for internal tool; acceptable for now

### 7. EtherNet/IP Port Hardcoded
**Issue:** pycomm3 uses port 44818; no option to change

**Impact:** Won't work on non-standard ports

**Likelihood:** Low for typical PLCs

**Mitigation:** Document in README, note as limitation

### 8. No Tag Value Caching
**Issue:** Each Tag Monitor refresh reads from PLC (no client-side cache)

**Trade-off:** Always fresh data vs. network load

**Decision:** Correct choice - users expect real-time values

### 9. UDT Expansion Threads Can Pile Up
**Issue:** If user rapidly expands many UDTs, create many threads

**Mitigation:** Already storing thread refs to prevent garbage collection

**Monitor:** Could add queue system if becomes performance issue

### 10. Module Editor State Not Persisted
**Issue:** If user edits and closes without saving, changes lost

**Current:** No auto-save, no "discard changes?" prompt

**Trade-off:** Simplicity vs. safety

**Mitigation:** Clear messaging that unsaved changes will be lost

## Testing Strategy

### Unit Testing
- Not yet implemented (future: pytest)
- Would test:
  - SimModule serialization/deserialization
  - Tag alias validation
  - Type detection in Quick Write
  - PlcConnection error handling

### Integration Testing
- Currently manual:
  1. Connect to test PLC
  2. Load tags
  3. Create and run simulation module
  4. Write tags and monitor
  5. Save/load modules
- Should formalize in GitHub Actions

### Edge Cases to Test
- Very large programs (1000+ tags)
- Nested UDTs (UDT within UDT within UDT)
- Script errors (syntax, missing aliases, division by zero)
- Disconnect during simulation
- Missing simulation tags at startup
- Protected/inaccessible tags

## Code Quality Notes

### Technical Debt
- No error handling for corrupted .simmod files
- Script syntax is validated (compile-only) live and before run; semantic/runtime
  errors are still only caught at execution (reported with a line number)
- `syntax_highlighter.py` (`PythonHighlighter`) is now unused — the QScintilla
  lexer replaced it; candidate for deletion
- `ModuleEditorWidget` has a duplicate `_add_user_input` definition (the second
  shadows the first) — harmless but worth cleaning up
- UI layout hardcoded (no responsive layout for different screen sizes)
- No logging levels (all logs go to logger, not organized by severity)
- Minimal comments in complex methods

### Improvements for Next Dev
1. Add docstrings to all public methods
2. Extract magic numbers to constants (1000ms heartbeat, 0.2 lag factor, etc.)
3. Add comprehensive error messages for common issues
4. Create unit tests for SimModule/SimEngine
5. Consider config file for defaults (default IP, heartbeat interval, etc.)

## Performance Characteristics

**Tag Monitor with 100 tags:**
- Initial load: 2-3 seconds (depends on PLC response time)
- Auto-refresh (1s): Responsive, no lag
- Manual refresh: Instant

**Simulation Loop (1s interval):**
- Read 5 input tags: ~50ms
- Execute 50-line Python script: ~1ms
- Write 3 output tags: ~50ms
- Total: ~100ms overhead per cycle
- Plenty of headroom for 1s interval

**Tag Browser:**
- Load 600 tags: 15-30 seconds (background thread, doesn't block UI)
- Search: Instant (local filtering)
- Expand UDT (10 members): ~500ms (network read)

**PyInstaller Executable:**
- Size: ~90MB (includes Python + PyQt6 + pycomm3)
- Startup time: 3-5 seconds on typical hardware
- Acceptable for occasional use

## Deployment Notes

### Installation Methods
1. **GitHub package:** `pip install git+https://github.com/...`
   - Best for: Developers, regular users
   - Update: `pip install --upgrade`

2. **Standalone .exe:** Download from GitHub Releases
   - Best for: Non-technical users, offline networks
   - No Python required

3. **Inno Setup Installer:** (future)
   - Best for: Enterprise distribution
   - Creates Start Menu shortcuts, uninstaller

### Version Update Process
1. Update `pyproject.toml` version
2. Update `plc_test_suite/__init__.py` version
3. Commit: `git commit -m "Release v1.26.02.01"`
4. Tag: `git tag v1.26.02.01`
5. Push: `git push && git push origin v1.26.02.01`
6. GitHub Actions (future): Auto-builds .exe
7. Create GitHub Release with release notes

## Future Developer Handoff

**If I step away:**

1. **High Priority Issues:**
   - Tag alias validation (prevent script errors)
   - Auto-save modules
   - Graceful handling of missing simulation tags

2. **High Value Additions:**
   - Test result logging/export
   - Example modules library
   - Network simulation features

3. **Know Before Starting:**
   - pycomm3 documentation: https://github.com/ottowayi/pycomm3
   - PyQt6 signals/slots: https://doc.qt.io/qt-6/signals-slots.html
   - Threading in PyQt: Background threads can't update UI; use signals
   - Python `exec()` safety: Script namespace is sandboxed but not truly safe
   - Git workflow: Use branches for features, squash commits before merge

## Changelog

### v1.26.06.03
- Scripts can end the simulation gracefully with `stop("reason")` /
  `stop_simulation()` — disables sim tags and resets the UI like the Stop button
  (previously `exit()` would kill the loop thread but leave the PLC in sim mode)

### v1.26.06.02
- Script editors upgraded to QScintilla: line-number gutter, auto-indent, brace
  matching, bracket/quote auto-close
- Alias-aware autocomplete (tag/user-input aliases + keywords + builtins +
  packaged module members) and Jedi hover help / signatures
- Compile-only syntax checking: live error markers plus a pre-run gate that blocks
  starting a syntax-broken script; runtime errors now report the script line number
- `math` / `time` / `random` packaged and available in scripts, with an
  "Included Libraries" reference on the Simulation Modules tab
- Added offscreen smoke tests; `PLC-Test-Suite.spec` is now tracked (bundles
  QScintilla + jedi/parso)

### v1.26.06.01
- Reconciled version numbering to the documented `MAJOR.YY.MM.MINOR` scheme
  (package files previously read `0.1.0`)
- Confirmed Python syntax highlighting ships in the script editors (init/loop) —
  the prior release build predated the highlighter
- Includes earlier fixes: optional heartbeat tag for connection status, tag-browser
  UDT expansion, safer PLC disconnect handling, simulation-tab layout spacing
- CLAUDE.md developer guide now tracked in the repository

### v1.26.02.01 (Initial Release)
- Complete simulation module engine
- All four main tabs functional
- Tag browser with UDT expansion
- User input controls
- Syntax highlighting
- Comprehensive documentation
- Ready for production use

---

**Last Updated:** June 2026  
**Maintainer:** Joel Ryan  
**License:** Internal Use
