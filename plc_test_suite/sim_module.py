"""
Simulation Module - Data model and execution engine

Each SimModule represents one test/simulation function with:
  - sim_tags:     tags written True at start, False at end (enable simulation mode)
  - input_tags:   tags only read by the simulation (aliased)
  - output_tags:  tags written by the simulation (aliased)
  - init_script:  Python code run once at startup
  - loop_script:  Python code run every N seconds
"""

import json
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from pathlib import Path
from plc_test_suite.user_inputs import UserInput

logger = logging.getLogger(__name__)


@dataclass
class TagEntry:
    """A tag with an associated alias for use in scripts"""
    tag: str       # Full PLC tag name e.g. "LT_Tank_001.inp_sim"
    alias: str     # Short alias used in scripts e.g. "tank_level"


@dataclass
class SimModule:
    """
    A self-contained simulation/test module.

    Attributes:
        name:           Human-readable module name
        description:    Optional description of what this module tests
        sim_tags:       List of tag names to set True on start / False on stop
        input_tags:     Tags read by the simulation (with aliases)
        output_tags:    Tags written by the simulation (with aliases)
        init_script:    Python snippet run once when module starts
        loop_script:    Python snippet run every `interval_seconds`
        interval_seconds: How often the loop script executes
    """
    name: str = "New Module"
    description: str = ""
    sim_tags: List[str] = field(default_factory=list)
    input_tags: List[TagEntry] = field(default_factory=list)
    output_tags: List[TagEntry] = field(default_factory=list)
    user_inputs: List[UserInput] = field(default_factory=list)  # NEW LINE
    init_script: str = "# One-time setup script\n# Read inputs and set initial output values\n"
    loop_script: str = "# Loop script - runs every interval\n# Use aliases to read/write tags\n"
    interval_seconds: float = 1.0

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "sim_tags": self.sim_tags,
            "input_tags": [{"tag": t.tag, "alias": t.alias} for t in self.input_tags],
            "output_tags": [{"tag": t.tag, "alias": t.alias} for t in self.output_tags],
            "user_inputs": [{"alias": u.alias, "input_type": u.input_type, "label": u.label, 
                            "default_value": u.default_value, "min_val": u.min_val, "max_val": u.max_val} 
                            for u in self.user_inputs],  # NEW LINE
            "init_script": self.init_script,
            "loop_script": self.loop_script,
            "interval_seconds": self.interval_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimModule":
        module = cls(
            name=data.get("name", "Unnamed"),
            description=data.get("description", ""),
            sim_tags=data.get("sim_tags", []),
            input_tags=[TagEntry(**t) for t in data.get("input_tags", [])],
            output_tags=[TagEntry(**t) for t in data.get("output_tags", [])],
            user_inputs=[UserInput(**u) for u in data.get("user_inputs", [])],  # Defaults to [] if key missing
            init_script=data.get("init_script", ""),
            loop_script=data.get("loop_script", ""),
            interval_seconds=data.get("interval_seconds", 1.0),
        )
        return module

    def save(self, path: str):
        """Save this module to a JSON file"""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved module '{self.name}' to {path}")

    @classmethod
    def load(cls, path: str) -> "SimModule":
        """Load a module from a JSON file"""
        with open(path, "r") as f:
            data = json.load(f)
        logger.info(f"Loaded module from {path}")
        return cls.from_dict(data)


# -------------------------------------------------------------------------
# Execution Engine
# -------------------------------------------------------------------------

class SimEngine:
    """
    Runs a SimModule against a live PLC connection.

    Lifecycle:
        start()  → enable sim tags → run init_script → start loop thread
        stop()   → stop loop → disable sim tags
    """

    def __init__(self, module: SimModule, plc, log_callback: Optional[Callable] = None):
        self.module = module
        self.plc = plc
        self.log_callback = log_callback or (lambda msg, level="info": None)

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stop requested from within a script via stop()
        self._stop_requested = False
        # Called (with no args) once the engine has fully stopped, so the UI can
        # reset. May be invoked from the loop thread — keep it thread-safe.
        self.on_finished: Optional[Callable] = None
        # Guards the one-time cleanup so button-stop and script-stop don't race
        self._finalize_lock = threading.Lock()
        self._finalized = False

        # Called as on_sample(elapsed_seconds, {alias: value}) each cycle so a
        # trend can record data. Fired from the loop thread — keep it thread-safe.
        self.on_sample: Optional[Callable] = None
        self._t0 = 0.0

        # Shared namespace for scripts - persists across loop iterations
        self._script_ns: Dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Enable sim tags, run init script, start loop. Returns True on success."""
        if self._running:
            self._log("Module is already running", "warn")
            return False

        self._log(f"Starting module: {self.module.name}")
        self._t0 = time.time()

        # 1. Enable simulation tags
        if not self._set_sim_tags(True):
            return False

        # 2. Build initial namespace from current PLC values
        self._script_ns = self._build_namespace()
        if self._script_ns is None:
            self._set_sim_tags(False)
            return False

        # 3. Run init script
        if self.module.init_script.strip():
            if not self._exec_script(self.module.init_script, "init_script"):
                self._set_sim_tags(False)
                return False
            # After init, flush any output changes back to PLC
            self._flush_outputs()

        # Emit an initial sample at t≈0 so trends start from the baseline
        self._emit_sample()

        # 4. Start loop thread
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log(f"Module running (interval: {self.module.interval_seconds}s)")
        return True

    def set_user_input_callback(self, callback):
        """Set callback to get current user input values"""
        self._user_input_callback = callback

    def stop(self):
        """Stop the loop and disable sim tags (called by the UI / app close)."""
        self._running = False
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._finalize()

    def _request_stop(self, reason: str = ""):
        """Injected into scripts as ``stop()``. Requests a graceful shutdown:
        the loop finishes the current iteration, flushes outputs, then stops."""
        self._stop_requested = True
        detail = f": {reason}" if reason else ""
        self._log(f"Stop requested by script{detail}")

    def _finalize(self):
        """Idempotent shutdown: disable sim tags, log, and notify the UI.
        Safe to call from either the loop thread or the UI thread."""
        with self._finalize_lock:
            if self._finalized:
                return
            self._finalized = True
        self._running = False
        self._set_sim_tags(False)
        self._log(f"Module stopped: {self.module.name}")
        if self.on_finished:
            try:
                self.on_finished()
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"on_finished callback failed: {e}")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_current_values(self) -> Dict[str, object]:
        """Return a snapshot of current alias values for display"""
        return {k: v for k, v in self._script_ns.items()
                if not k.startswith("_")}

    def trendable_aliases(self) -> List[str]:
        """Alias names a trend can plot: input + output + user-input aliases."""
        names = [t.alias for t in self.module.input_tags]
        names += [t.alias for t in self.module.output_tags]
        names += [u.alias for u in self.module.user_inputs]
        return names

    def _sample_values(self) -> Dict[str, float]:
        """Numeric snapshot of the trendable aliases for the current cycle."""
        sample = {}
        for alias in self.trendable_aliases():
            val = self._script_ns.get(alias)
            if isinstance(val, bool):
                sample[alias] = 1.0 if val else 0.0
            elif isinstance(val, (int, float)):
                sample[alias] = float(val)
        return sample

    def _emit_sample(self):
        """Send the current cycle's values to the trend callback (if any)."""
        if not self.on_sample:
            return
        try:
            self.on_sample(time.time() - self._t0, self._sample_values())
        except Exception as e:  # pragma: no cover - trend must never break the loop
            logger.warning(f"on_sample callback failed: {e}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _loop(self):
        """Background thread - runs loop_script every interval_seconds"""
        while self._running and not self._stop_requested:
            start = time.time()

            # Re-read inputs into namespace
            self._refresh_inputs()

            # Inject user input values into namespace  # NEW
            if hasattr(self, '_user_input_callback'):  # NEW
                user_vals = self._user_input_callback()  # NEW
                self._script_ns.update(user_vals)  # NEW

            # Execute loop script
            if self.module.loop_script.strip():
                self._exec_script(self.module.loop_script, "loop_script")

            # Flush outputs back to PLC (the final computed values are written
            # even when the script just requested a stop)
            self._flush_outputs()

            # Record a trend sample for this cycle
            self._emit_sample()

            # If the script called stop(), shut down gracefully now
            if self._stop_requested:
                break

            # Sleep for remainder of interval
            elapsed = time.time() - start
            sleep_time = max(0, self.module.interval_seconds - elapsed)
            time.sleep(sleep_time)

        # If the loop ended because a script requested stop, finalize here
        # (the UI button path finalizes via stop() instead).
        if self._stop_requested:
            self._finalize()

    def _build_namespace(self) -> Optional[Dict]:
        """
        Build the script execution namespace.
        Reads all input and output tags from the PLC and maps them to aliases.
        """
        all_tags = (
            [(t.alias, t.tag) for t in self.module.input_tags] +
            [(t.alias, t.tag) for t in self.module.output_tags]
        )

        # Whitelisted modules available to scripts (kept in sync with
        # WHITELIST_MODULES in sim_tab.py). `time` is aliased locally to avoid
        # shadowing the module-level import used by this engine.
        import math
        import time as _time
        import random
        ns = {"math": math, "time": _time, "random": random}

        # Let scripts request a graceful stop, e.g. `if estop: stop("reason")`
        ns["stop"] = self._request_stop
        ns["stop_simulation"] = self._request_stop

        if not all_tags:
            return ns

        tag_names = [tag for _, tag in all_tags]
        values = self.plc.read_tags(tag_names)

        for alias, tag in all_tags:
            val = values.get(tag)
            if val is None:
                self._log(f"Warning: could not read tag '{tag}' (alias: {alias})", "warn")
                val = 0  # Default to 0 so scripts don't crash on None
            ns[alias] = val

        return ns

    def _refresh_inputs(self):
        """Re-read input tags and update namespace"""
        if not self.module.input_tags:
            return
        tag_names = [t.tag for t in self.module.input_tags]
        values = self.plc.read_tags(tag_names)
        for entry in self.module.input_tags:
            val = values.get(entry.tag)
            if val is not None:
                self._script_ns[entry.alias] = val

    def _flush_outputs(self):
        """Write output alias values back to PLC tags"""
        if not self.module.output_tags:
            return
        pairs = []
        for entry in self.module.output_tags:
            val = self._script_ns.get(entry.alias)
            if val is not None:
                pairs.append((entry.tag, val))
        if pairs:
            self.plc.write_tags(pairs)

    def _set_sim_tags(self, state: bool) -> bool:
        """Write True/False to all sim_tags"""
        if not self.module.sim_tags:
            return True
        pairs = [(tag, state) for tag in self.module.sim_tags]
        success = self.plc.write_tags(pairs)
        action = "Enabled" if state else "Disabled"
        if success:
            self._log(f"{action} simulation for {len(pairs)} tag(s)")
        else:
            self._log(f"Failed to {action.lower()} some simulation tags", "error")
        return success

    def _exec_script(self, script: str, label: str) -> bool:
        """
        Execute a user script in the shared namespace.
        Returns True on success, False on exception.
        """
        try:
            exec(compile(script, label, "exec"), self._script_ns)
            return True
        except Exception as e:
            # Find the line number inside the user's script (frames compiled
            # with `label` as the filename)
            lineno = None
            tb = e.__traceback__
            while tb is not None:
                if tb.tb_frame.f_code.co_filename == label:
                    lineno = tb.tb_lineno
                tb = tb.tb_next
            where = f" (line {lineno})" if lineno else ""
            self._log(f"Script error in {label}{where}: {type(e).__name__}: {e}", "error")
            return False

    def _log(self, msg: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        if level == "error":
            logger.error(msg)
        elif level == "warn":
            logger.warning(msg)
        else:
            logger.info(msg)
        self.log_callback(full_msg, level)
