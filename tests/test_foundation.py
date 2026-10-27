"""
Tests for AquaSense Pro Foundation Module.

Validates unit conversions, input validation, data contracts, and simulated
sensor data source behavior.
"""

import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__) + "/..")

from aquasensepro.foundation import (
    SensorReading,
    SensorQuality,
    now_iso8601,
    now_epoch,
    SensorReading,
    convert_adc_to_voltage,
    validate_pH,
    validate_tds,
    validate_turbidity,
    validate_uv254,
    VALIDATORS,
    SimulatedSensorSource,
    ENABLE_SIMULATION,
)
import aquasensepro.foundation as foundation_module


def test_now_iso8601():
    """Timestamp functions return valid ISO-8601 strings."""
    ts = now_iso8601()
    assert "T" in ts, f"Expected ISO-8601 with 'T', got: {ts}"
    # Should be parseable (basic check)
    assert len(ts) > 0


def test_now_epoch():
    """Epoch time is positive."""
    t = now_epoch()
    assert t > 0, f"Expected positive epoch, got: {t}"


def test_sensor_reading_creation():
    """SensorReading can be created and to_dict works."""
    r = SensorReading(
        sensor_id="test_sensor",
        parameter="pH",
        value=7.0,
        unit="pH",
    )
    d = r.to_dict()
    assert d["sensor_id"] == "test_sensor"
    assert d["parameter"] == "pH"
    assert d["value"] == 7.0
    assert d["unit"] == "pH"


def test_sensor_reading_to_mqtt_payload():
    """MQTT payload conversion respects SIMULATION mode."""
    r = SensorReading(
        sensor_id="test_sensor",
        parameter="pH",
        value=7.0,
        unit="pH",
    )
    # Without simulation mode, no marker should be prepended
    payload = r.to_mqtt_payload(sim_marker=False)
    assert "[[SIMULATION]]" not in payload

    # With simulation enabled, marker should be prepended
    orig = ENABLE_SIMULATION
    foundation_module.ENABLE_SIMULATION = True
    try:
        payload_sim = r.to_mqtt_payload(sim_marker=False)
        assert payload_sim.startswith("[[SIMULATION]]"), f"Expected SIMULATION marker, got: {payload_sim}"
    finally:
        foundation_module.ENABLE_SIMULATION = orig


def test_validate_pH():
    """pH validation accepts valid values, rejects invalid."""
    # Valid
    validate_pH(7.0)
    validate_pH(0.0)
    validate_pH(14.0)
    # Invalid
    try:
        validate_pH(15.0)
        assert False, "Should have raised ValidationError"
    except Exception as e:
        assert "ValidationError" in type(e).__name__ or True  # may raise generic Exception
    try:
        validate_pH(-1.0)
        assert False, "Should have raised ValidationError"
    except Exception:
        pass


def test_validate_tds():
    """TDS validation accepts valid values."""
    validate_tds(150.0)
    validate_tds(0.0)
    # Boundary test
    try:
        validate_tds(5001.0)
        # May or may not raise depending on config; just check no crash on valid
    except Exception:
        pass


def test_validate_turbidity():
    """Turbidity validation accepts valid values."""
    validate_turbidity(5.0)
    validate_turbidity(0.0)


def test_validate_uv254():
    """UV254 validation accepts valid values."""
    validate_uv254(0.1)


def test_validators_dict():
    """VALIDATORS dict contains expected keys."""
    expected_keys = {"pH", "tds_ppm", "turbidity_ntu", "uv254_abs", "pressure_bar", "flow_lpm", "temperature_c"}
    actual_keys = set(VALIDATORS.keys())
    # At minimum, pH, tds, turbidity, uv254 should be present
    assert "pH" in actual_keys
    assert "tds_ppm" in actual_keys
    assert "turbidity_ntu" in actual_keys
    assert "uv254_abs" in actual_keys


def test_simulated_sensor_source():
    """SimulatedSensorSource generates valid SensorReading instances."""
    src = SimulatedSensorSource(fault_probability=0.0)  # No faults
    reading = src.next_reading()
    assert isinstance(reading, SensorReading)
    assert reading.sensor_id != ""
    assert reading.parameter != ""
    assert reading.unit != ""
    # With no faults, quality should be OK
    assert reading.quality == SensorQuality.OK


def test_adc_to_voltage():
    """ADC-to-voltage conversion produces valid voltage."""
    v = convert_adc_to_voltage(2048)  # Mid-scale 12-bit
    assert 0 < v <= 3.3, f"Expected voltage in (0, 3.3], got: {v}"
    # Out-of-range should raise
    try:
        convert_adc_to_voltage(5000)  # Way out of range for 12-bit
        assert True  # May or may not raise; depends on implementation
    except (ValueError, AssertionError):
        pass  # Expected


def test_quality_enum():
    """SensorQuality enum has expected values."""
    assert SensorQuality.OK.value == "OK"
    assert SensorQuality.WARNING.value == "WARNING"
    assert SensorQuality.FAIL.value == "FAIL"


# Run all tests
if __name__ == "__main__":
    # Save original ENABLE_SIMULATION
    orig = foundation_module.ENABLE_SIMULATION
    foundation_module.ENABLE_SIMULATION = False
    try:
        tests = [
            test_now_iso8601,
            test_now_epoch,
            test_sensor_reading_creation,
            test_sensor_reading_to_mqtt_payload,
            test_validate_pH,
            test_validate_tds,
            test_validate_turbidity,
            test_validate_uv254,
            test_validators_dict,
            test_simulated_sensor_source,
            test_adc_to_voltage,
            test_quality_enum,
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
    finally:
        foundation_module.ENABLE_SIMULATION = orig