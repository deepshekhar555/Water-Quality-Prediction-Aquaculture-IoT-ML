"""
AquaSense Pro — Water-Quality Monitoring Module (Priority 2)

Handles pH, TDS, turbidity, and UV254 data for the domestic RO purifier system.
Domain: RO purifier water (specified in BioTwinLabs_Track2.pdf), NOT aquaculture pond water.

Key distinctions from the original aquaculture project:
- Original: predicted Dissolved Oxygen (DO) and WaterQuality score using pond data.
- New: handles TDS, pH, Turbidity (NTU), UV254 (organic absorption proxy) for drinking water.
- Original: DO = 0.14 * pH^0.01 * exp(0.2 * T) * 0.15 * Turbidity^0.01
- New: No DO prediction. Direct sensing of TDS, pH, Turbidity, UV254.
- Original: WaterQuality = (0.2 * T) + (0.1 * pH) + (0.15 * DO) - (0.05 * Turbidity)
- New: No composite WaterQuality score. Each parameter tracked independently with thresholds.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime

import math
from typing import Dict, List, Optional, Any
from datetime import datetime

from .foundation import (
    SensorReading,
    SensorQuality,
    now_iso8601,
    ENABLE_SIMULATION,
    validate_pH,
    validate_tds,
    validate_turbidity,
    validate_uv254,
)


# ---------------------------------------------------------------------------
# Threshold Configuration
# ---------------------------------------------------------------------------
class ThresholdConfig:
    """Configurable threshold values for abnormal-reading alerts."""

    def __init__(self):
        self.pH_low_warning: float = 6.5
        self.pH_high_warning: float = 8.5
        self.pH_critical_low: float = 4.0
        self.pH_critical_high: float = 11.0
        self.tds_low_warning: float = 50.0
        self.tds_high_warning: float = 500.0
        self.turbidity_clear: float = 5.0
        self.turbidity_murky: float = 10.0
        self.uv254_normal: float = 0.1
        self.uv254_elevated: float = 0.3
        self.pressure_interlock: float = 4.5
        self.flow_min_lpm: float = 0.5
        self.flow_max_lpm: float = 5.0
        self.stale_reading_timeout_s: int = 90


# Global threshold config instance
thresholds = ThresholdConfig()


# ---------------------------------------------------------------------------
# Water-Quality Measurement Record
# ---------------------------------------------------------------------------
@dataclass
class WaterQualityMeasurement:
    """A cohesive set of water-quality measurements taken at one point in time."""
    timestamp: str
    pH: Optional[float] = None
    tds_ppm: Optional[float] = None
    turbidity_ntu: Optional[float] = None
    uv254_abs: Optional[float] = None
    temperature_c: Optional[float] = None
    pH_status: str = "normal"
    tds_status: str = "normal"
    turbidity_status: str = "clear"
    uv254_status: str = "normal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "pH": self.pH,
            "pH_status": self.pH_status,
            "tds_ppm": self.tds_ppm,
            "tds_status": self.tds_status,
            "turbidity_ntu": self.turbidity_ntu,
            "turbidity_status": self.turbidity_status,
            "uv254_abs": self.uv254_abs,
            "uv254_status": self.uv254_status,
            "temperature_c": self.temperature_c,
        }

    def to_mqtt_payload(self) -> str:
        import json
        return json.dumps(self.to_dict())


# ---------------------------------------------------------------------------
# Threshold Evaluation
# ---------------------------------------------------------------------------
def evaluate_pH_status(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value < thresholds.pH_critical_low or value > thresholds.pH_critical_high:
        return "critical"
    if value < thresholds.pH_low_warning or value > thresholds.pH_high_warning:
        return "warning"
    return "normal"


def evaluate_tds_status(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value < thresholds.tds_low_warning:
        return "low_warning"
    if value > thresholds.tds_high_warning:
        return "high_warning"
    return "normal"


def evaluate_turbidity_status(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value <= thresholds.turbidity_clear:
        return "clear"
    if value <= thresholds.turbidity_murky:
        return "murky"
    return "dirty"


def evaluate_uv254_status(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value < thresholds.uv254_normal:
        return "normal"
    if value <= thresholds.uv254_elevated:
        return "elevated"
    return "high"


# ---------------------------------------------------------------------------
# Measurement Ingestion Pipeline
# ---------------------------------------------------------------------------
def ingest_measurements(raw_readings: List[SensorReading]) -> WaterQualityMeasurement:
    ts = now_iso8601()
    params: Dict[str, float] = {}
    for r in raw_readings:
        if r.quality == SensorQuality.FAIL:
            continue
        params[r.parameter] = r.value

    pH = params.get("pH")
    tds = params.get("tds_ppm")
    turbidity = params.get("turbidity_ntu")
    uv254 = params.get("uv254_abs")
    temp = params.get("temperature_c")

    if pH is not None:
        validate_pH(pH)
    if tds is not None:
        validate_tds(tds)
    if turbidity is not None:
        validate_turbidity(turbidity)
    if uv254 is not None:
        validate_uv254(uv254)

    m = WaterQualityMeasurement(
        timestamp=ts,
        pH=pH,
        tds_ppm=tds,
        turbidity_ntu=turbidity,
        uv254_abs=uv254,
        temperature_c=temp,
    )

    m.pH_status = evaluate_pH_status(m.pH)
    m.tds_status = evaluate_tds_status(m.tds_ppm)
    m.turbidity_status = evaluate_turbidity_status(m.turbidity_ntu)
    m.uv254_status = evaluate_uv254_status(m.uv254_abs)

    return m


# ---------------------------------------------------------------------------
# Historical Record
# ---------------------------------------------------------------------------
class HistoricalRecord:
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self.records: List[WaterQualityMeasurement] = []

    def add(self, m: WaterQualityMeasurement) -> None:
        self.records.append(m)
        if len(self.records) > self.max_entries:
            self.records = self.records[-self.max_entries:]

    def get_recent(self, n: int = 10) -> List[WaterQualityMeasurement]:
        """Return the n most recent measurements, newest first."""
        if not self.records:
            return []
        return list(reversed(self.records[-n:])) if n >= 0 else []

    def get_by_status(self, status: str, parameter: str = None) -> List[WaterQualityMeasurement]:
        result = []
        for m in self.records:
            if parameter is None:
                if (m.pH_status == status or m.tds_status == status or
                    m.turbidity_status == status or m.uv254_status == status):
                    result.append(m)
            elif parameter == "pH" and m.pH_status == status:
                result.append(m)
            elif parameter == "tds" and m.tds_status == status:
                result.append(m)
            elif parameter == "turbidity" and m.turbidity_status == status:
                result.append(m)
            elif parameter == "uv254" and m.uv254_status == status:
                result.append(m)
        return result

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.records]


# Global historical record instance
history = HistoricalRecord()


# ---------------------------------------------------------------------------
# End of Module
# Documentation of claims that have and have not been validated:
#
# - Threshold evaluations (pH, TDS, turbidity, UV254 status) use configurable
#   defaults typical for RO purifier drinking water. These are baseline monitoring
#   only — they do not declare water safe or unsafe. Physical laboratory testing
#   is required for any safety claim (see Safety_and_Validation.md).
#
# - UV254 status evaluation flags "elevated" absorbance as an alert. UV254 is a
#   proxy for Dissolved Organic Carbon (DOC), NOT a direct measurement of every
#   organic contaminant. Do not claim that UV254 detects specific contaminants.
#   See PDF: "Clearly distinguish directly measured values from ML-estimated values."
#   and "Do not claim that UV254 directly measures every organic contaminant."
#
# - Turbidity status uses three bands: clear (≤5 NTU), murky (5–10 NTU), dirty (>10 NTU).
#   These bands are indicative only; real water-quality classification requires
#   laboratory analysis.
#
# - TDS threshold warnings (low <50 ppm, high >500 ppm) are indicative of
#   remineralization needs or taste concerns. Actual health-based limits
#   (EPA secondary MCLs) should be referenced for production deployments.
#
# - All threshold values are CONFIGURABLE and should be calibrated per hardware.
#   Do not use these defaults as absolute safety boundaries without empirical validation.
#
# - The composite "WaterQuality score" from the original aquaculture project
#   (DO-based formula) is NOT reused. Each parameter is tracked independently.
#   Mixing aquaculture labels (DO, pond water, fish health) with purifier
#   predictions is explicitly prohibited per Phase Three of the task.
#
# - Simulation mode generates plausible but synthetic data. Do not use
#   simulation values for any production decision or safety interlock.
#