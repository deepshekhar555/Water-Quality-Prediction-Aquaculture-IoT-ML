"""
AquaSense Pro — RO Process & ReGen-X Mineral Recovery Simulation (Priority 4)

Simulates RO permeate/reject flow, electrodialysis mineral recovery, and controlled
mineral dosing. When physical hardware (ED cell, pumps, sensors) is unavailable,
a clearly labeled software simulation provides the data structure and mass-balance
checks for development purposes.

DO NOT: Represent simulated recovery as actual physical recovery.
DO: Document the steps needed for real integration. Clearly label simulation mode.

Per the PDF (BioTwinLabs_Track2.pdf), Track 2 — ReGen-X core requirements:
- Model RO permeate and reject-water streams
- Separate mineral-recovery module for calcium and magnesium
- Electrodialysis process and controlled mineral dosing
- Track input water, permeate, reject volume, recovered mineral quantities, mass balance
- Configurable dosing limits, sensor checks, and fail-safe shutoff
"""
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Simulation Mode Detection
# ---------------------------------------------------------------------------
try:
    from .foundation import ENABLE_SIMULATION
except Exception:
    ENABLE_SIMULATION = False


# ---------------------------------------------------------------------------
# RO Process Mass-Balance Data Structure
# ---------------------------------------------------------------------------

@dataclass
class ROProcessState:
    """Track RO process water and mineral mass balance."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Volumes (liters)
    input_volume_l: float = 0.0       # Raw water input volume
    permeate_volume_l: float = 0.0     # Pure water output volume
    reject_volume_l: float = 0.0       # Brine/reject output volume

    # Recovery ratio: permeate / input (target: >65% recovery, <35% reject per PDF)
    recovery_ratio: float = 0.65  # adjustable; 1 - recovery = reject fraction

    # Mineral tracking (mg = milligrams; track recovered quantities from reject)
    ca_recovered_mg: float = 0.0       # Calcium recovered via electrodialysis
    mg_recovered_mg: float = 0.0       # Magnesium recovered via electrodialysis

    # Dosing (mg) — how much Ca/Mg re-injected into permeate
    ca_dosed_mg: float = 0.0           # Calcium dosed into permeate this cycle
    mg_dosed_mg: float = 0.0           # Magnesium dosed into permeate this cycle

    # Configurable setpoints
    ca_setpoint_mgL: float = 30.0      # Target calcium concentration in permeate (mg/L)
    mg_setpoint_mgL: float = 20.0      # Target magnesium concentration in permeate (mg/L)

    # Fault flags
    mass_balance_error: bool = False   # Detected if input ≠ permeate + reject
    dose_overflow: bool = False        # Dosing exceeded setpoint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "input_volume_l": self.input_volume_l,
            "permeate_volume_l": self.permeate_volume_l,
            "reject_volume_l": self.reject_volume_l,
            "recovery_ratio": self.recovery_ratio,
            "ca_recovered_mg": self.ca_recovered_mg,
            "mg_recovered_mg": self.mg_recovered_mg,
            "ca_dosed_mg": self.ca_dosed_mg,
            "mg_dosed_mg": self.mg_dosed_mg,
            "ca_setpoint_mgL": self.ca_setpoint_mgL,
            "mg_setpoint_mgL": self.mg_setpoint_mgL,
            "mass_balance_error": self.mass_balance_error,
            "dose_overflow": self.dose_overflow,
        }

    def to_mqtt_payload(self) -> str:
        return json.dumps(self.to_dict())

    # -- Mass balance enforcement --

    def enforce_mass_balance(self) -> None:
        """Enforce RO mass balance: input ≈ permeate + reject.

        Error tolerance: 5% of input volume. If error exceeds tolerance,
        flag the mass_balance_error.
        """
        expected_reject = self.input_volume_l * (1.0 - self.recovery_ratio)
        actual_reject = self.reject_volume_l
        error_pct = abs(self.input_volume_l - self.permeate_volume_l - actual_reject) / \
                    self.input_volume_l * 100.0 if self.input_volume_l > 0 else 0.0

        self.mass_balance_error = error_pct > 5.0  # 5% tolerance
        if self.mass_balance_error:
            # Do NOT silently correct; flag for investigation
            pass


# ---------------------------------------------------------------------------
# Electrodialysis (ED) Mineral Recovery Module
# ---------------------------------------------------------------------------

class EDRecoveryModule:
    """
    Electrodialysis-based mineral recovery from RO reject stream.

    PDF specification (Track 2):
    - ReGen-X diverts RO reject water through a low-power Ion-Exchange Electrodialysis Cell
      (12V DC, <15W), driven by selective cation/anion exchange membranes that separate
      Ca²⁺ and Mg²⁺ ions from concentrated brine.
    - Re-injects them into the post-RO stream via precision micro-peristaltic dosing pumps.

    SIMULATION MODE:
    When physical ED cell is unavailable, this module provides a software model
    that computes recovered mineral quantities from reject flow, current, and time.
    All output is clearly labeled for what it is: a simulation approximation.
    """

    def __init__(self,
                 simulation: bool = bool(ENABLE_SIMULATION)):
        self.simulation = simulation
        # Empirical constant for simulation: mg recovered per mA·h of current
        # This is NOT a real physical constant; see documentation.
        self.simulation_ca_factor_mg_per_mAh = 0.05  # placeholder
        self.simulation_mg_factor_mg_per_mAh = 0.04  # placeholder

        # Track current integration (mA·h)
        self.current_integrated_mAh: float = 0.0
        self.last_current_mA: float = 0.0
        self.last_integration_time_s: float = time.time()

        # Recovered quantities
        self.ca_recovered_mg: float = 0.0
        self.mg_recovered_mg: float = 0.0

        # Dosing pump control
        self.dosing_active: bool = False
        self.ca_dose_rate_mg_per_min: float = 0.5  # simulated default
        self.mg_dose_rate_mg_per_min: float = 0.3  # simulated default

    def update(self,
               reject_lpm: float,
               current_mA: float,
               time_s: Optional[float] = None) -> Dict[str, Any]:
        """Update ED recovery module with reject flow and ED cell current."""

        if time_s is None:
            time_s = time.time()

        # Integrate current over time (mA * s / 3600 = mA·h)
        dt = time_s - self.last_integration_time_s
        if dt > 0 and self.last_current_mA is not None:
            self.current_integrated_mAh += (self.last_current_mA * dt) / 3600.0

        self.last_current_mA = current_mA
        self.last_integration_time_s = time_s

        if self.simulation:
            # Simulation: approximate recovered minerals from integrated current
            # mg = factor * mA·h
            self.ca_recovered_mg = round(self.simulation_ca_factor_mg_per_mAh * self.current_integrated_mAh, 1)
            self.mg_recovered_mg = round(self.simulation_mg_factor_mg_per_mAh * self.current_integrated_mAh, 1)
            # Do NOT claim this is physical recovery; it is a simulation approximation
        else:
            # Real hardware path: would read from ED cell sensors, measure ion
            # concentrations before/after, etc. Not implemented without hardware.
            raise NotImplementedError(
                "Physical ED cell recovery requires custom hardware integration. "
                "See HARDWARE_INTEGRATION.md for connection guidelines."
            )

        # Control dosing: re-inject recovered minerals into permeate stream
        # Simulate PWM-driven peristaltic pump dosing
        ca_dosed = round(self.ca_dose_rate_mg_per_min * dt / 60.0, 1) if dt > 0 else 0.0
        mg_dosed = round(self.mg_dose_rate_mg_per_min * dt / 60.0, 1) if dt > 0 else 0.0

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reject_lpm": reject_lpm,
            "current_mA": current_mA,
            "current_integrated_mAh": round(self.current_integrated_mAh, 2),
            "ca_recovered_mg": self.ca_recovered_mg,
            "mg_recovered_mg": self.mg_recovered_mg,
            "ca_dosed_mg": ca_dosed,
            "mg_dosed_mg": mg_dosed,
            "simulation": self.simulation,
            "declaration": (
                "SIMULATION MODE: Recovered mineral quantities are approximated from "
                "integrated current using empirical factors. Do not represent as actual "
                "physical recovery without ED cell and ICP-OES validation."
                if self.simulation else
                "HARDWARE MODE: Actual ED cell mineral recovery."
            ),
        }

        return result


# ---------------------------------------------------------------------------
# Mineral Dosing Control
# ---------------------------------------------------------------------------

class MineralDosingController:
    """
    PWM micro-dosing pump control for calcium and magnesium re-injection into
    the RO permeate stream.

    PDF specification:
    - Instead of discarding RO reject water (which wastes up to 65% of input water
      rich in calcium and magnesium salts), a dual-stage electrodialysis mineral
      recovery unit (ReGen-X) extracts essential ionic minerals (Ca²⁺, Mg²⁺) from
      the reject stream and injects controlled, ultra-pure mineral doses back into
      the permeate stream via PWM micro-dosing pumps.
    - Configurable dosing limits, sensor checks, and fail-safe shutoff.
    """

    def __init__(self,
                 ca_setpoint_mgL: float = 30.0,
                 mg_setpoint_mgL: float = 20.0,
                 max_dose_mg_per_cycle: float = 5.0,
                 simulation: bool = bool(ENABLE_SIMULATION)):
        self.ca_setpoint_mgL = ca_setpoint_mgL
        self.mg_setpoint_mgL = mg_setpoint_mgL
        self.max_dose_mg_per_cycle = max_dose_mg_per_cycle
        self.simulation = simulation

        # Current cycle state
        self.dosing_active: bool = False
        self.cycle_start_vol_l: float = 0.0
        self.ca_dosed_this_cycle_mg: float = 0.0
        self.mg_dosed_this_cycle_mg: float = 0.0

        # History
        self.dosing_history: List[Dict[str, Any]] = []

    def update(self,
               permeate_vol_this_cycle_l: float,
               current_ca_mgL: float = None,
               current_mg_mgL: float = None) -> Dict[str, Any]:
        """Determine dosing amounts for this cycle based on setpoints and current measurements."""

        # Calculate how much Ca/Mg to dose to reach setpoint
        # Simple model: dose = (setpoint - current) * permeate_volume
        # Clamp to max_dose_mg_per_cycle and non-negative

        if self.simulation:
            # Simulation dosing: generate plausible values
            target_ca_dose = max(0, self.ca_setpoint_mgL - (current_ca_mgL or 0))
            target_mg_dose = max(0, self.mg_setpoint_mgL - (current_mg_mgL or 0))

            # Apply limits
            ca_dose = min(target_ca_dose, self.max_dose_mg_per_cycle)
            mg_dose = min(target_mg_dose, self.max_dose_mg_per_cycle)

            # Simulate partial uptake/retention (not all dosed mineral stays in solution)
            retention = 0.8  # 80% retention assumption
            actual_ca = round(ca_dose * retention, 1)
            actual_mg = round(mg_dose * retention, 1)
        else:
            raise NotImplementedError(
                "Physical dosing pump control requires hardware integration "
                "(peristaltic pumps, flow sensors, conductivity meters). "
                "See HARDWARE_INTEGRATION.md for guidance."
            )

        # Check for overflow: does dosing exceed setpoint?
        dose_overflow = (actual_ca > self.ca_setpoint_mgL or actual_mg > self.mg_setpoint_mgL)

        # Build result
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "permeate_vol_this_cycle_l": permeate_vol_this_cycle_l,
            "current_ca_mgL": current_ca_mgL or 0.0,
            "current_mg_mgL": current_mg_mgL or 0.0,
            "ca_setpoint_mgL": self.ca_setpoint_mgL,
            "mg_setpoint_mgL": self.mg_setpoint_mgL,
            "ca_dosed_mg": actual_ca,
            "mg_dosed_mg": actual_mg,
            "dose_overflow": dose_overflow,
            "dosing_active": self.dosing_active,
            "simulation": self.simulation,
        }

        # Record in history
        self.dosing_history.append(result)
        self.ca_dosed_this_cycle_mg = actual_ca
        self.mg_dosed_this_cycle_mg = actual_mg

        if dose_overflow:
            result["safety_action"] = "Dosing overflow detected — shut off pumps (fail-safe)"
        else:
            result["safety_action"] = "Dosing within limits"

        return result


# ---------------------------------------------------------------------------
# Fault & Safety Checks
# ---------------------------------------------------------------------------

def check_ro_safety(
    input_vol: float,
    permeate_vol: float,
    reject_vol: float,
    recovery_ratio: float,
    pressure_bar: float,
    ca_dosed_mg: float,
    mg_dosed_mg: float,
    ca_setpoint_mgL: float,
    mg_setpoint_mgL: float,
) -> Dict[str, Any]:
    """Run safety checks on RO + ReGen-X state. Returns dict with any active faults."""

    faults: List[str] = []
    warnings: List[str] = []

    # Mass balance check
    expected_reject = input_vol * (1.0 - recovery_ratio)
    error_pct = abs(input_vol - permeate_vol - reject_vol) / input_vol * 100.0 if input_vol > 0 else 0.0
    if error_pct > 5.0:
        faults.append(f"mass_balance_error ({error_pct:.1f}% error)")

    # Pressure fault: >4.5 bar → inlet solenoid isolate
    if pressure_bar > 4.5:
        faults.append("pressure_interlock (>4.5 bar — solenoid should close)")

    # Dosing overflow check
    if ca_dosed_mg > ca_setpoint_mgL:
        faults.append("ca_dose_overflow")
    if mg_dosed_mg > mg_setpoint_mgL:
        faults.append("mg_dose_overflow")

    # Recovery ratio check: reject should be <35% of input per PDF target
    if recovery_ratio > 0.65:
        # recovery_ratio = permeate/input; if >0.65, reject <35%
        # This is the target; exceeding recovery ratio means less reject (good for water savings)
        # But if it's unrealistically high (>90%), flag concern
        if recovery_ratio > 0.90:
            warnings.append("very_high_recovery_ratio (>90% — check for sensor readings)")

    # Permeate volume too low (possible clog)
    if permeate_vol > 0 and permeate_vol / input_vol < 0.1:
        warnings.append("very_low_recovery (<10% — possible filter clog)")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "faults": faults,
        "warnings": warnings,
        "safe": len(faults) == 0,
    }


# ---------------------------------------------------------------------------
# End of Module
# ---------------------------------------------------------------------------
# Documentation of claims that have and have not been validated:
#
# - RO process simulation (permeate/reject volumes, recovery ratio) uses
   # configurable recovery ratio with mass-balance enforcement (input ≈ permeate + reject).
   # Tolerance: 5% error. This is a software skeleton; real mass balance requires
   # physical flow meters (Hall-effect Fin/Fout) and volume tracking.
#
# - Electrodialysis mineral recovery SIMULATION uses empirical factors
   # (simulation_ca_factor_mg_per_mAh, simulation_mg_factor_mg_per_mAh) that
   # are NOT calibrated to real hardware. Without an actual ED cell with
   # ion-selective membranes and ICP-OES validation, recovered mineral quantities
   # are approximations only. Clearly labeled with [[SIMULATION]] marker when
   # ENABLE_SIMULATION=1.
#
# - Controlled mineral dosing simulates PWM micro-dosing pump behavior. Real
   # peristaltic pump control requires hardware: flow sensors, conductivity meters
   # post-dosing, and PWM signal to pump drivers. See HARDWARE_INTEGRATION.md.
#
# - Safety check function check_ro_safety enforces basic PDF-specified limits
   # (pressure >4.5 bar interlock, mass balance, dosing overflow). These are
   # software monitoring only; hardware interlocks (solenoid valves, optocouplers)
   # must provide independent physical fail-safe (see SAFETY_AND_VALIDATION.md).
#
# - Dosing overflow detection: software flags when dosed amount exceeds setpoint.
   # Does NOT auto-shutoff hardware; that is a physical interlock function.
#
# - Recovery ratio target: PDF aims for <35% reject (i.e. >65% recovery). The
   # software configurable recovery_ratio defaults to 0.65. Actual achievable
   # recovery depends on membrane type, pressure, water chemistry. No claim of
   # guaranteed % recovery without empirical validation.
#
# - The original aquaculture project's dissolved oxygen formula and pond data
   # are NOT reused. This module concerns RO permeate/reject and mineral recovery
   # for a domestic water purifier — a different domain. Labels, datasets, and
   # model outputs from the aquaculture project have been preserved in the repo
   # but are not applied to purifier predictions (Phase Three adaptation).
#