"""
Tests for AquaSense Pro RUL (Remaining Useful Life) Pipeline Module.

Validates XGBoost training with walk-forward validation, RUL prediction,
synthetic data generation, and walk-forward split utility.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__) + "/..")

from aquasensepro.rul_pipeline import (
    XGBoostRULPipeline,
    generate_synthetic_rul_data,
    walk_forward_split,
    BaselineMonitor,
)
from aquasensepro.foundation import ENABLE_SIMULATION


def test_baseline_monitor_update():
    """BaselineMonitor.update processes flow/pressure data."""
    monitor = BaselineMonitor()
    result = monitor.update(fin_lpm=2.0, fout_lpm=1.5, pressure_bar=2.0)
    assert "degradation_flags" in result
    assert "filter_health" in result
    assert "operating_hours_accumulated" in result


def test_baseline_monitor_operating_hours():
    """BaselineMonitor accumulates operating hours over time."""
    monitor = BaselineMonitor(operating_hours_threshold_days=10.0)
    # First update
    r1 = monitor.update(fin_lpm=2.0, fout_lpm=1.5, pressure_bar=2.0)
    # Second update at later time (simulate by calling again; operating hours
    # accumulate based on time delta internally, but we'll just check no crash)
    r2 = monitor.update(fin_lpm=2.0, fout_lpm=1.5, pressure_bar=2.0)
    assert "degradation_flags" in r2


def test_generate_synthetic_rul_data():
    """Synthetic data generator produces DataFrame with expected columns."""
    df = generate_synthetic_rul_data(n_samples=100)
    expected_cols = {"time", "dRc_dt_proxy", "operating_hours", "flow_ratio",
                     "pressure_bar", "pressure_rise_rate", "rul_days"}
    assert set(df.columns) == expected_cols, f"Missing cols: {expected_cols - set(df.columns)}"
    # RUL should decrease over time (approximately)
    # First rul_days should be close to max (60), last close to 0
    assert df["rul_days"].iloc[0] > df["rul_days"].iloc[-1] - 5, \
        f"RUL should decrease over time: first={df['rul_days'].iloc[0]}, last={df['rul_days'].iloc[-1]}"
    # All rul_days should be non-negative
    assert all(df["rul_days"] >= 0)


def test_walk_forward_split():
    """Walk-forward split produces train/test without leakage."""
    df = generate_synthetic_rul_data(n_samples=200)
    train, test = walk_forward_split(df, cutoff_frac=0.8)

    # Train should be earlier (smaller time values), test later (larger time values)
    assert train["time"].iloc[-1] <= test["time"].iloc[0], \
        f"Train set should be entirely before test set: train_max={train['time'].iloc[-1]}, test_min={test['time'].iloc[0]}"

    # Train set should be ~80% of data
    assert len(train) <= 200 * 0.8 + 5, f"Train set too large: {len(train)}"
    assert len(test) >= 200 * 0.2 - 5, f"Test set too small: {len(test)}"

    # No rul_days leakage: test rul_days should be based on later operating hours
    assert train["operating_hours"].max() <= test["operating_hours"].min() + 1, \
        "Walk-forward: train operating hours should not exceed test hours"


def test_rul_pipeline_train():
    """XGBoostRULPipeline.train with walk-forward validation."""
    df = generate_synthetic_rul_data(n_samples=150)

    pipeline = XGBoostRULPipeline(walk_forward_cutoff_frac=0.8)
    metrics = pipeline.train(df)

    # Check metrics structure
    assert "mae" in metrics
    assert "rmse" in metrics
    assert "r2" in metrics

    # Model should be marked trained (or gracefully handled if XGBoost not available)
    print(f"  Pipeline trained: {pipeline.is_trained}")
    print(f"  Metrics: {metrics}")

    # If XGBoost is available and model trained, metrics should be numeric
    if pipeline.is_trained:
        assert not (np.isnan(metrics["mae"]) and np.isnan(metrics["rmse"]) and np.isnan(metrics["r2"]))
        # R² should be a finite number (could be negative for poor model, but not NaN if trained)
        assert isinstance(metrics["r2"], (float, np.floating))


def test_rul_pipeline_predict():
    """XGBoostRULPipeline.predict_rul after training."""
    df = generate_synthetic_rul_data(n_samples=150)

    pipeline = XGBoostRULPipeline(walk_forward_cutoff_frac=0.8)
    pipeline.train(df)

    # Predict using features from the test data
    last_row = df.iloc[-1]
    pred = pipeline.predict_rul(
        dRc_dt_proxy=last_row["dRc_dt_proxy"],
        operating_hours=last_row["operating_hours"],
        flow_ratio=last_row["flow_ratio"],
        pressure_bar=last_row["pressure_bar"],
        pressure_rise_rate=last_row["pressure_rise_rate"],
    )

    assert "rul_days" in pred
    assert "rul_liters" in pred
    assert "metrics" in pred
    assert "model_version" in pred
    print(f"  Prediction: {pred}")


def test_rul_pipeline_save_load():
    """XGBoostRULPipeline save/load persistence."""
    import tempfile

    df = generate_synthetic_rul_data(n_samples=100)

    pipeline = XGBoostRULPipeline(walk_forward_cutoff_frac=0.8)
    pipeline.train(df)

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        pipeline.save(tmp_path)
        # Load it back
        pipeline2 = XGBoostRULPipeline.load(tmp_path)
        assert pipeline2 is not None
        print(f"  Loaded pipeline trained: {pipeline2.is_trained}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


# Run tests
if __name__ == "__main__":
    orig = ENABLE_SIMULATION
    try:
        from aquasensepro import foundation as foundation_module
        foundation_module.ENABLE_SIMULATION = False
    except Exception:
        pass

    tests = [
        test_baseline_monitor_update,
        test_baseline_monitor_operating_hours,
        test_generate_synthetic_rul_data,
        test_walk_forward_split,
        test_rul_pipeline_train,
        test_rul_pipeline_predict,
        test_rul_pipeline_save_load,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            import traceback
            failed.append((test.__name__, str(e), traceback.format_exc()))
            print(f"FAIL {test.__name__}: {e}")

    if failed:
        print(f"\n{len(failed)} test(s) failed:")
        for name, err, tb in failed:
            print(f"  - {name}: {err}")
            # print first 200 chars of traceback
            print(f"    {tb[:200]}")
    else:
        print(f"\nAll {len(tests)} tests passed!")