import unittest
from pathlib import Path

import pandas as pd

from aquasensepro.purifier_monitoring import (
    DEMO_SCENARIOS,
    make_demo_telemetry,
    prepare_telemetry,
)


class PurifierMonitoringTests(unittest.TestCase):
    def test_demo_rows_are_balanced_and_alarm_free(self):
        telemetry = prepare_telemetry(make_demo_telemetry(n_samples=12))

        self.assertEqual(len(telemetry), 12)
        self.assertLess(float(telemetry["mass_balance_error_pct"].max()), 1e-9)
        self.assertFalse(bool(telemetry["active_alarm"].any()))
        self.assertTrue(telemetry["tds_rejection_pct"].between(0, 100).all())

    def test_pressure_and_mass_balance_faults_are_flagged(self):
        raw = make_demo_telemetry(n_samples=3)
        raw.loc[2, "pressure_bar"] = 4.8
        raw.loc[1, "reject_lpm"] = 0.1

        telemetry = prepare_telemetry(raw)

        self.assertTrue(bool(telemetry.loc[2, "pressure_trip"]))
        self.assertTrue(bool(telemetry.loc[1, "mass_balance_fault"]))
        self.assertTrue(bool(telemetry["active_alarm"].iloc[1:3].all()))

    def test_invalid_sensor_values_are_marked_as_faults(self):
        raw = make_demo_telemetry(n_samples=3)
        raw["ph"] = raw["ph"].astype(object)
        raw.loc[1, "ph"] = "bad reading"

        telemetry = prepare_telemetry(raw)

        self.assertTrue(bool(telemetry.loc[1, "sensor_fault"]))
        self.assertTrue(bool(telemetry.loc[1, "active_alarm"]))

    def test_out_of_range_sensor_values_are_marked_as_faults(self):
        raw = make_demo_telemetry(n_samples=3)
        raw.loc[1, "uv254_abs"] = 3.5

        telemetry = prepare_telemetry(raw)

        self.assertTrue(bool(telemetry.loc[1, "sensor_fault"]))
        self.assertTrue(bool(telemetry.loc[1, "active_alarm"]))

    def test_missing_schema_columns_are_rejected(self):
        raw = pd.DataFrame({"timestamp": ["2026-10-29T10:00:00Z"]})

        with self.assertRaisesRegex(ValueError, "Missing telemetry columns"):
            prepare_telemetry(raw)

    def test_demo_requires_two_rows_for_trends(self):
        with self.assertRaisesRegex(ValueError, "At least two samples"):
            make_demo_telemetry(n_samples=1)

    def test_demo_scenarios_exercise_their_matching_alarms(self):
        self.assertEqual(len(DEMO_SCENARIOS), 4)
        pressure = prepare_telemetry(make_demo_telemetry(scenario="Pressure trip"))
        sensor = prepare_telemetry(make_demo_telemetry(scenario="Sensor fault"))
        flow = prepare_telemetry(make_demo_telemetry(scenario="Flow imbalance"))

        self.assertTrue(bool(pressure.iloc[-1]["pressure_trip"]))
        self.assertTrue(bool(sensor.iloc[-1]["sensor_fault"]))
        self.assertTrue(bool(flow.iloc[-1]["mass_balance_fault"]))

    def test_unknown_demo_scenario_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown demo scenario"):
            make_demo_telemetry(scenario="Unverified result")

    def test_existing_firmware_csv_is_accepted_with_unavailable_channels(self):
        raw = pd.DataFrame(
            {
                "sample_id": ["100"],
                "timestamp_ms": ["1234"],
                "pH": ["7.1"],
                "temperature_c": ["25.4"],
                "turbidity_ntu": ["32.0"],
            }
        )

        telemetry = prepare_telemetry(raw)
        latest = telemetry.iloc[0]

        self.assertAlmostEqual(latest["ph"], 7.1)
        self.assertAlmostEqual(latest["temperature_c"], 25.4)
        self.assertAlmostEqual(latest["turbidity_ntu"], 32.0)
        self.assertTrue(pd.isna(latest["raw_tds_ppm"]))
        self.assertTrue(pd.isna(latest["recovery_pct"]))
        self.assertFalse(bool(latest["sensor_fault"]))

    def test_bundled_sample_csv_loads_as_twelve_simulated_rows(self):
        sample_path = Path(__file__).resolve().parents[1] / "purifier_telemetry_demo_simulated.csv"
        raw = pd.read_csv(sample_path)

        telemetry = prepare_telemetry(raw)

        self.assertEqual(len(telemetry), 12)
        self.assertTrue(raw["data_origin"].eq("SIMULATED_EXAMPLE").all())
        self.assertFalse(bool(telemetry["active_alarm"].any()))


if __name__ == "__main__":
    unittest.main()