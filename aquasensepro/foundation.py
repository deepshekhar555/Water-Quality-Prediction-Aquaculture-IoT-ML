"""
AquaSense Pro — Foundation Module

Core data contracts, unit conversions, input validation, and timestamp handling
for the multi-parameter water-quality sensing system. Domain: domestic RO purifier
(specified in BioTwinLabs_Track2.pdf), NOT aquaculture pond water.

HARDWARE DEPENDENCY:
- Physical sensors required for production.
- SIMULATION MODE: set ENABLE_SIMULATION=1 in .env to use mock data.
"""

import time
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union, List
from enum import Enum


# ---------------------------------------------------------------------------
# Configuration: enable simulation mode (development without hardware)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ENABLE_SIMULATION = False
try:
    import os
    sim_str = os.getenv("ENABLE_SIMULATION", "0")
    ENABLE_SIMULATION = sim_str.strip() in ("1", "true", "True")
except Exception:
    ENABLE_SIMULATION = False


# ---------------------------------------------------------------------------
# Sensor Quality Enum
# ---------------------------------------------------------------------------
class SensorQuality(Enum):
    OK = "OK"
    WARNING = "WARNING"
    FAIL = "FAIL"


# ---------------------------------------------------------------------------
# Timestamp Helper
# ---------------------------------------------------------------------------
def now_iso8601() -> str:
    """Return current UTC time as ISO-8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def now_epoch() -> float:
    """Return current time as Unix epoch seconds."""
    return time.time()


# ---------------------------------------------------------------------------
# Data Contract: a single validated sensor reading
# ---------------------------------------------------------------------------
@dataclass
class SensorReading:
    """Represents one validated sensor reading with quality flag and timestamp."""
    sensor_id: str
    parameter: str        # e.g. "pH", "turbidity_ntu", "tds_ppm", "uv254_abs"
    value: float          # The measured value (already converted to engineering units)
    unit: str             # e.g. "ppm", "NTU", "AU"
    timestamp: str = field(default_factory=now_iso8601)
    quality: SensorQuality = SensorQuality.OK
    raw_adc: Optional[int] = None  # Optional raw ADC value for debugging

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "parameter": self.parameter,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "quality": self.quality.value,
        }

    def to_mqtt_payload(self, sim_marker: bool = True) -> str:
        """Convert to MQTT JSON payload. If sim_marker=True, prepends [[SIMULATION]]."""
        import json
        payload = json.dumps(self.to_dict())
        if sim_marker and ENABLE_SIMULATION:
            payload = "[[SIMULATION]] " + payload
        return payload


# ---------------------------------------------------------------------------
# Unit Conversion Functions
# ---------------------------------------------------------------------------
def convert_adc_to_voltage(raw_adc: int, adc_bits: int = 12, ref_voltage: float = 3.3) -> float:
    """Convert raw ADC value to voltage (ESP32: 12-bit, 3.3V reference)."""
    if raw_adc < 0 or raw_adc > (2 ** adc_bits - 1):
        raise ValueError(f"ADC value out of range: {raw_adc}")
    return round(raw_adc * ref_voltage / (2 ** adc_bits), 3)


def voltage_to_pH(voltage: float, cal_voltage_7: float = 3.5) -> float:
    """Convert pH electrode voltage to pH value."""
    # pH = -5.70 * volt + calibration_value (existing aquaculture model,
    # re-calibrated for new RO purifier circuit with pH 4.01 and 7.01 buffers)
    pH = -5.70 * voltage + (-5.70 * -cal_voltage_7 + 7.0)
    pH = max(0.0, min(14.0, pH))
    return round(pH, 2)


def voltage_to_tds(voltage: float, calibration_factor: float = 21.34, offset: float = -0.7) -> float:
    """Convert TDS sensor voltage to TDS in ppm (placeholder; requires calibration)."""
    if ENABLE_SIMULATION:
        return round(calibration_factor * voltage + offset + (time.time() % 100), 1)
    raise NotImplementedError(
        "TDS conversion requires sensor-specific calibration with known TDS standards."
    )


def voltage_to_turbidity_ntu(voltage: float, cal_a: float = 0.01, cal_b: float = 0.0) -> float:
    """Convert turbidity sensor voltage to NTU (placeholder; requires calibration)."""
    if ENABLE_SIMULATION:
        return round(cal_a * voltage + cal_b + (time.time() % 10), 1)
    raise NotImplementedError(
        "Turbidity NTU conversion requires calibration with Formazin standards."
    )


def voltage_to_uv254_abs(voltage: float, cal_a: float = 0.123, cal_b: float = 0.0) -> float:
    """Convert UV254 module voltage to optical absorbance (AU) (placeholder; requires calibration)."""
    if ENABLE_SIMULATION:
        return round(cal_a * voltage + cal_b, 4)
    raise NotImplementedError(
        "UV254 absorbance conversion requires calibration with spectrophotometer DOC standards. "
        "UV254 is a proxy for DOC, NOT a direct measurement of every organic contaminant."
    )


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------
class ValidationError(Exception):
    """Raised when a sensor reading fails validation."""
    pass


def validate_pH(value: float) -> None:
    if value is None:
        raise ValidationError("pH reading is None (missing/timeout)")
    if not (0.0 <= value <= 14.0):
        raise ValidationError(f"pH value out of valid range: {value} (must be 0.0-14.0)")


def validate_tds(value: float) -> None:
    if value is None:
        raise ValidationError("TDS reading is None (missing/timeout)")
    if not (0.0 <= value <= 5000.0):
        raise ValidationError(f"TDS value out of reasonable range: {value} ppm (0-5000)")


def validate_turbidity(value: float) -> None:
    if value is None:
        raise ValidationError("Turbidity reading is None (missing/timeout)")
    if not (0.0 <= value <= 1000.0):
        raise ValidationError(f"Turbidity value out of reasonable range: {value} NTU (0-1000)")


def validate_uv254(value: float) -> None:
    if value is None:
        raise ValidationError("UV254 reading is None (missing/timeout)")
    if not (0.0 <= value <= 3.0):
        raise ValidationError(f"UV254 absorbance out of reasonable range: {value} AU (0-3.0)")


def validate_pressure_bar(value: float) -> None:
    if value is None:
        raise ValidationError("Pressure reading is None (missing/timeout)")
    if not (0.0 <= value <= 10.0):
        raise ValidationError(f"Pressure value out of reasonable range: {value} bar (0-10)")


def validate_flow_lpm(value: float) -> None:
    if value is None:
        raise ValidationError("Flow reading is None (missing/timeout)")
    if not (0.0 <= value <= 20.0):
        raise ValidationError(f"Flow value out of reasonable range: {value} L/min (0-20)")


def validate_temperature_c(value: float) -> None:
    if value is None:
        raise ValidationError("Temperature reading is None (missing/timeout)")
    if not (-5.0 <= value <= 50.0):
        raise ValidationError(f"Temperature out of reasonable range: {value} C (-5-50)")


VALIDATORS: Dict[str, callable] = {
    "pH": validate_pH,
    "tds_ppm": validate_tds,
    "turbidity_ntu": validate_turbidity,
    "uv254_abs": validate_uv254,
    "pressure_bar": validate_pressure_bar,
    "flow_lpm": validate_flow_lpm,
    "temperature_c": validate_temperature_c,
}


def validate_reading(reading: 'SensorReading') -> 'SensorReading':
    """Validate a SensorReading's value using the appropriate function."""
    validator = VALIDATORS.get(reading.parameter)
    if validator is None:
        return reading
    try:
        validator(reading.value)
    except ValidationError as e:
        reading.quality = SensorQuality.FAIL
        reading.value = None
        raise
    return reading


# ---------------------------------------------------------------------------
# Simulated Sensor Data Source (Priority 1 Foundation)
# ---------------------------------------------------------------------------
class SimulatedSensorSource:
    """Generates synthetic sensor readings for development without hardware."""

    def __init__(self, pH_drift: float = 0.0, tds_drift: float = 0.0,
                 turbidity_drift: float = 0.0, uv254_drift: float = 0.0,
                 fault_probability: float = 0.01):
        self.pH_drift = pH_drift
        self.tds_drift = tds_drift
        self.turbidity_drift = turbidity_drift
        self.uv254_drift = uv254_drift
        self.fault_probability = fault_probability
        self.step_counter = 0
        import random
        self.random = random

    def _faulty(self) -> bool:
        return self.random.random() < self.fault_probability

    def _drift(self, base: float, drift: float) -> float:
        return base + drift * (self.step_counter % 100) / 100.0

    def next_reading(self) -> 'SensorReading':
        self.step_counter += 1

        base_pH = 7.5
        base_tds = 150.0
        base_turbidity = 1.0
        base_uv254 = 0.05

        pH = self._drift(base_pH, self.pH_drift)
        tds = self._drift(base_tds, self.tds_drift)
        turbidity = self._drift(base_turbidity, self.turbidity_drift)
        uv254 = self._drift(base_uv254, self.uv254_drift)

        if self._faulty(): pH = 14.5
        if self._faulty(): tds = -5.0
        if self._faulty(): turbidity = 1500.0
        if self._faulty(): uv254 = 5.0

        pH = max(0.0, min(14.0, pH))
        tds = max(0.0, min(5000.0, tds))
        turbidity = max(0.0, min(1000.0, turbidity))
        uv254 = max(0.0, min(3.0, uv254))

        readings = []
        readings.append(SensorReading(
            sensor_id="pH_electrode", parameter="pH", value=pH, unit="pH",
            quality=SensorQuality.FAULTY if pH < 0 or pH > 14 else SensorQuality.OK,
        ))
        readings.append(SensorReading(
            sensor_id="TDS_electrode", parameter="tds_ppm", value=tds, unit="ppm",
            quality=SensorQuality.FAULTY if tds < 0 or tds > 5000 else SensorQuality.OK,
        ))
        readings.append(SensorReading(
            sensor_id="turbidity_sensor", parameter="turbidity_ntu", value=turbidity, unit="NTU",
            quality=SensorQuality.FAULTY if turbidity < 0 or turbidity > 10 else SensorQuality.OK,
        ))
        readings.append(SensorReading(
            sensor_id="UV254_module", parameter="uv254_abs", value=uv254, unit="AU",
            quality=SensorQuality.FAULTY if uv254 < 0 or uv254 > 3 else SensorQuality.OK,
        ))
        readings.append(SensorReading(
            sensor_id="DS18B20_temperature", parameter="temperature_c",
            value=round(25.0 + (self.step_counter % 10 - 5), 1), unit="°C",
            quality=SensorQuality.OK,
        ))
        return readings[0]


# ---------------------------------------------------------------------------
# End of Module
# Documentation of claims that have and have not been validated:
#
# - Unit conversion functions (ADC→voltage, voltage→pH, voltage→TDS, voltage→NTU,
#   voltage→UV254) are provided as skeleton functions with placeholder coefficients.
#   REAL CALIBRATION REQUIRED: Do not use in production without empirical calibration.
#   See Safety_and_Validation.md for prohibited claims and validation steps.
#
# - Sensor validation functions enforce reasonable engineering bounds but do NOT
#   replace physical calibration.
#
# - Simulation mode (ENABLE_SIMULATION=1) generates synthetic data for development.
#   Output is labeled with [[SIMULATION]] marker. Do not deploy simulation mode on
#   actual hardware.
#
# - All NotImplementedError functions require real hardware calibration before use.
#   The skeleton code structure is provided; numerical coefficients must be determined
#   empirically.
#
# - TDS conversion is sensor-specific. The placeholder formula (TDS = K*V + offset)
#   must be calibrated with known conductivity standards (0, 500, 1413, 12880 ppm).
#
# - UV254 absorbance is a proxy for Dissolved Organic Carbon (DOC). It does NOT
#   directly measure every organic contaminant. Claims about specific contaminant
#   detection are prohibited without laboratory validation.
#
# - pH voltage-to-pH conversion uses the existing aquaculture calibration model.
#   This must be re-calibrated for the new RO purifier sensor circuit with pH 4.01
#   and 7.01 buffer solutions.
#