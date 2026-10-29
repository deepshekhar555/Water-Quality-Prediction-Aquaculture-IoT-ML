import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from aquasensepro.aquaculture import (
    available_observed_targets,
    evaluate_models,
    normalize_measurements,
)


def sample_frame(count: int = 50) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Sample No": range(1, count + 1),
            "Avg. PH": [6.8 + (index % 7) * 0.1 for index in range(count)],
            "(°C)": [24.0 + (index % 5) * 0.5 for index in range(count)],
            "(NTU)": [2.0 + (index % 6) * 1.5 for index in range(count)],
        }
    )


def test_normalize_project_headers_and_derive_values():
    measurements, summary = normalize_measurements(sample_frame())
    assert len(measurements) == 50
    assert summary["valid_rows"] == 50
    assert measurements.loc[0, "pH"] == 6.8
    assert measurements.loc[0, "Dissolved oxygen estimate (mg/L)"] > 0
    assert "Water quality score estimate" in measurements


def test_quality_summary_tracks_incomplete_and_out_of_range_rows():
    raw = pd.DataFrame(
        {
            "Sample No": [1, 2, 3],
            "Avg. PH": [7.0, None, 15.0],
            "(°C)": [25.0, 25.0, 25.0],
            "(NTU)": [3.0, 3.0, 3.0],
        }
    )
    measurements, summary = normalize_measurements(raw)
    assert len(measurements) == 1
    assert summary["incomplete_rows"] == 1
    assert summary["out_of_range_rows"] == 1


def test_knn_imputation_is_visible_per_sample():
    raw = sample_frame(20)
    raw.loc[3, "Avg. PH"] = None
    measurements, summary = normalize_measurements(raw, impute_missing=True)
    assert len(measurements) == 20
    assert summary["imputed_rows"] == 1
    assert "pH" in measurements.loc[3, "Imputed fields"]
    assert pd.notna(measurements.loc[3, "pH"])


def test_observed_targets_are_preferred_over_formula_estimates():
    raw = sample_frame()
    raw["Dissolved Oxygen (mg/L)"] = [5.0 + (index % 4) * 0.1 for index in range(50)]
    raw["Water Quality"] = [4.0 + (index % 9) * 0.1 for index in range(50)]
    measurements, _ = normalize_measurements(raw)
    targets = available_observed_targets(measurements)
    assert targets == [
        "Dissolved oxygen observed (mg/L)",
        "Water quality observed",
        "Water quality from observed DO",
    ]


def test_pond_holdout_validation_is_selected_when_groups_exist():
    raw = sample_frame()
    raw["Pond ID"] = [f"pond-{index % 5}" for index in range(50)]
    raw["Water Quality"] = [4.0 + (index % 11) * 0.08 for index in range(50)]
    measurements, _ = normalize_measurements(raw)
    scores, predictions = evaluate_models(measurements, "Water quality observed")
    assert set(scores["Validation"]) == {"5-fold pond-held-out"}
    assert len(predictions) == 50
    assert predictions["Random forest"].notna().all()


def test_chronological_validation_is_selected_when_timestamps_exist():
    raw = sample_frame()
    raw["Timestamp"] = pd.date_range("2026-01-01", periods=50, freq="h").astype(str)
    raw["Water Quality"] = [4.0 + (index % 11) * 0.08 for index in range(50)]
    measurements, _ = normalize_measurements(raw)
    scores, predictions = evaluate_models(measurements, "Water quality observed")
    assert set(scores["Validation"]) == {"chronological expanding-window"}
    assert 0 < len(predictions) < len(measurements)
    assert predictions["Linear regression"].notna().all()


def test_equation_fallback_is_identified_for_unlabeled_workbook():
    measurements, _ = normalize_measurements(sample_frame())
    scores, _ = evaluate_models(measurements, "Water quality score estimate")
    assert set(scores["Evaluation target"]) == {"Water quality score estimate"}
    assert set(scores["Validation"]) == {"5-fold shuffled sample split"}


if __name__ == "__main__":
    tests = [
        test_normalize_project_headers_and_derive_values,
        test_quality_summary_tracks_incomplete_and_out_of_range_rows,
        test_knn_imputation_is_visible_per_sample,
        test_observed_targets_are_preferred_over_formula_estimates,
        test_pond_holdout_validation_is_selected_when_groups_exist,
        test_chronological_validation_is_selected_when_timestamps_exist,
        test_equation_fallback_is_identified_for_unlabeled_workbook,
    ]
    for test in tests:
        test()
    print(f"All {len(tests)} aquaculture analytics tests passed.")
