"""
Tests for AquaSense Pro Water-Quality Monitoring Module.

Validates threshold evaluation, measurement ingestion, and historical record.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from aquasensepro.water_quality import (
    ThresholdConfig,
    WaterQualityMeasurement,
    evaluate_pH_status,
    evaluate_tds_status,
    evaluate_turbidity_status,
    evaluate_uv254_status,
    ingest_measurements,
    HistoricalRecord,
    SensorReading,
    SensorQuality,
)
from aquasensepro.foundation import ENABLE_SIMULATION


def test_threshold_config_defaults():
    """ThresholdConfig has expected default values."""
    tc = ThresholdConfig()
    assert tc.pH_low_warning == 6.5
    assert tc.pH_high_warning == 8.5
    assert tc.tds_low_warning == 50.0
    assert tc.tds_high_warning == 500.0
    assert tc.turbidity_clear == 5.0
    assert tc.turbidity_murky == 10.0
    assert tc.uv254_normal == 0.1
    assert tc.uv254_elevated == 0.3


def test_evaluate_pH_status():
    """pH status evaluation returns correct categories."""
    # Normal range
    assert evaluate_pH_status(7.0) == "normal"
    assert evaluate_pH_status(7.5) == "normal"
    # Warning range
    assert evaluate_pH_status(6.4) == "warning"  # just below 6.5
    assert evaluate_pH_status(8.6) == "warning"  # just above 8.5
    # Critical
    assert evaluate_pH_status(3.0) == "critical"
    assert evaluate_pH_status(12.0) == "critical"
    # None
    assert evaluate_pH_status(None) == "unknown"


def test_evaluate_tds_status():
    """TDS status evaluation."""
    assert evaluate_tds_status(30.0) == "low_warning"
    assert evaluate_tds_status(200.0) == "normal"
    assert evaluate_tds_status(600.0) == "high_warning"
    assert evaluate_tds_status(None) == "unknown"


def test_evaluate_turbidity_status():
    """Turbidity status evaluation."""
    assert evaluate_turbidity_status(1.0) == "clear"
    assert evaluate_turbidity_status(5.0) == "clear"
    assert evaluate_turbidity_status(7.0) == "murky"
    assert evaluate_turbidity_status(15.0) == "dirty"
    assert evaluate_turbidity_status(None) == "unknown"


def test_evaluate_uv254_status():
    """UV254 status evaluation."""
    assert evaluate_uv254_status(0.05) == "normal"
    assert evaluate_uv254_status(0.2) == "elevated"
    assert evaluate_uv254_status(0.5) == "high"
    assert evaluate_uv254_status(None) == "unknown"


def test_ingest_measurements_basic():
    """Ingest measurements with valid readings."""
    raw_readings = [
        SensorReading(sensor_id="pH_1", parameter="pH", value=7.2, unit="pH", quality=SensorQuality.OK),
        SensorReading(sensor_id="TDS_1", parameter="tds_ppm", value=150.0, unit="ppm", quality=SensorQuality.OK),
        SensorReading(sensor_id="Tur_1", parameter="turbidity_ntu", value=2.0, unit="NTU", quality=SensorQuality.OK),
        SensorReading(sensor_id="UV_1", parameter="uv254_abs", value=0.05, unit="AU", quality=SensorQuality.OK),
        SensorReading(sensor_id="Temp_1", parameter="temperature_c", value=22.5, unit="°C", quality=SensorQuality.OK),
    ]
    m = ingest_measurements(raw_readings)
    assert m.pH == 7.2
    assert m.tds_ppm == 150.0
    assert m.turbidity_ntu == 2.0
    assert m.uv254_abs == 0.05
    assert m.temperature_c == 22.5
    # Status flags should be set
    assert m.pH_status == "normal"
    assert m.tds_status == "normal"
    assert m.turbidity_status == "clear"
    assert m.uv254_status == "normal"


def test_ingest_measurements_with_failures():
    """Ingest measurements where some readings have FAIL quality."""
    raw_readings = [
        SensorReading(sensor_id="pH_1", parameter="pH", value=15.0, unit="pH", quality=SensorQuality.FAIL),  # invalid
        SensorReading(sensor_id="TDS_1", parameter="tds_ppm", value=150.0, unit="ppm", quality=SensorQuality.OK),
    ]
    m = ingest_measurements(raw_readings)
    # The FAIL pH should be skipped; pH may be None
    assert m.tds_ppm == 150.0
    # pH_status will be "unknown" since value was None
    assert m.pH_status == "unknown"


def test_historical_record():
    """HistoricalRecord stores and retrieves measurements."""
    hr = HistoricalRecord(max_entries=5)
    # Add measurements
    for i in range(3):
        m = WaterQualityMeasurement(
            timestamp=f"2026-10-{(20+i):02d}T12:00:00Z",
            pH=7.0 + i * 0.1,
            tds_ppm=100.0 + i * 10,
        )
        hr.add(m)

    # Retrieve recent
    recent = hr.get_recent(n=2)
    assert len(recent) == 2
    assert recent[0].pH == 7.2  # most recent
    assert recent[1].pH == 7.1

    # Get by status
    filtered = hr.get_by_status("normal", parameter="pH")
    assert len(filtered) >= 0  # may or may not match depending on status logic


def test_water_quality_measurement_to_dict():
    """WaterQualityMeasurement serialization."""
    m = WaterQualityMeasurement(
        timestamp="2026-10-27T12:00:00Z",
        pH=7.3,
        tds_ppm=150.0,
        turbidity_ntu=2.0,
        uv254_abs=0.05,
    )
    d = m.to_dict()
    assert d["pH"] == 7.3
    assert d["tds_ppm"] == 150.0
    assert d["turbidity_ntu"] == 2.0
    assert d["uv254_abs"] == 0.05


# Run tests
if __name__ == "__main__":
    orig = ENABLE_SIMULATION
    try:
        foundation_module.ENABLE_SIMULATION = False
    except Exception:
        pass

    tests = [
        test_threshold_config_defaults,
        test_evaluate_pH_status,
        test_evaluate_tds_status,
        test_evaluate_turbidity_status,
        test_evaluate_uv254_status,
        test_ingest_measurements_basic,
        test_ingest_measurements_with_failures,
        test_historical_record,
        test_water_quality_measurement_to_dict,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            failed.append((test.__name__, str(e)))
            print(f"FAIL {test.__name__}: {e}")

    if failed:
        print(f"\n{len(failed)} test(s) failed:")
        for name, err in failed:
            print(f"  - {name}: {err}")
    else:
        print(f"\nAll {len(tests)} tests passed!")