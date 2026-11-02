"""Telemetry preparation and transparent demo data for the purifier dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd


TELEMETRY_COLUMNS = [
    "timestamp",
    "ph",
    "temperature_c",
    "raw_tds_ppm",
    "permeate_tds_ppm",
    "turbidity_ntu",
    "uv254_abs",
    "pressure_bar",
    "feed_lpm",
    "permeate_lpm",
    "reject_lpm",
    "calcium_mg_l",
    "magnesium_mg_l",
    "filter_operating_l",
]

NUMERIC_COLUMNS = [column for column in TELEMETRY_COLUMNS if column != "timestamp"]
SENSOR_COLUMNS = [
    "ph",
    "temperature_c",
    "raw_tds_ppm",
    "permeate_tds_ppm",
    "turbidity_ntu",
    "uv254_abs",
    "pressure_bar",
    "feed_lpm",
    "permeate_lpm",
    "reject_lpm",
    "calcium_mg_l",
    "magnesium_mg_l",
    "filter_operating_l",
]
PLAUSIBLE_RANGES = {
    "ph": (0, 14),
    "temperature_c": (-5, 50),
    "raw_tds_ppm": (0, 5000),
    "permeate_tds_ppm": (0, 5000),
    "turbidity_ntu": (0, 1000),
    "uv254_abs": (0, 3),
    "pressure_bar": (0, 10),
    "feed_lpm": (0, 20),
    "permeate_lpm": (0, 20),
    "reject_lpm": (0, 20),
    "calcium_mg_l": (0, 1000),
    "magnesium_mg_l": (0, 1000),
    "filter_operating_l": (0, float("inf")),
}

HEADER_ALIASES = {
    "ph": {"ph", "phact"},
    "temperature_c": {"temperaturec", "tempc", "temperature"},
    "turbidity_ntu": {"turbidityntu", "turbidity"},
    "raw_tds_ppm": {"rawtdsppm", "feedtdsppm"},
    "permeate_tds_ppm": {"permeatetdsppm", "permeatetds"},
    "uv254_abs": {"uv254abs", "uv254"},
    "pressure_bar": {"pressurebar", "pressure"},
    "feed_lpm": {"feedlpm", "inletlpm"},
    "permeate_lpm": {"permeatelpm", "productlpm"},
    "reject_lpm": {"rejectlpm", "brinelpm"},
    "calcium_mg_l": {"calciummgl", "calciummgperliter"},
    "magnesium_mg_l": {"magnesiummgl", "magnesiummgperliter"},
    "filter_operating_l": {"filteroperatingl", "filtervolume"},
}


def _header_key(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def prepare_telemetry(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize partial sensor telemetry without inventing absent measurements."""
    if raw.empty:
        raise ValueError("The telemetry file contains no rows.")

    source = raw.copy()
    columns_by_key = {_header_key(column): column for column in source.columns}
    timestamp_column = next(
        (
            columns_by_key[key]
            for key in ("receivedat", "timestamp", "datetime", "recordedat")
            if key in columns_by_key
        ),
        None,
    )
    uptime_column = columns_by_key.get("timestampms")
    mapped_columns: dict[str, object] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        mapped = next(
            (columns_by_key[alias] for alias in aliases if alias in columns_by_key),
            None,
        )
        if mapped is not None:
            mapped_columns[canonical] = mapped

    if timestamp_column is None and uptime_column is None:
        raise ValueError("Missing telemetry columns: timestamp or timestamp_ms")
    if not mapped_columns:
        raise ValueError("Missing telemetry columns: at least one supported measurement")

    frame = pd.DataFrame(index=source.index)
    if timestamp_column is not None:
        frame["timestamp"] = pd.to_datetime(source[timestamp_column], errors="coerce", utc=True)
    else:
        uptime_ms = pd.to_numeric(source[uptime_column], errors="coerce")
        elapsed = pd.to_timedelta(uptime_ms - uptime_ms.min(), unit="ms")
        frame["timestamp"] = pd.Timestamp.now(tz="UTC") - (elapsed.max() - elapsed)

    for column in NUMERIC_COLUMNS:
        source_column = mapped_columns.get(column)
        if source_column is None:
            frame[column] = np.nan
            continue
        values = pd.to_numeric(source[source_column], errors="coerce")
        frame[column] = values.where(np.isfinite(values))

    frame = frame.sort_values("timestamp", na_position="last").reset_index(drop=True)
    observed_columns = [column for column in SENSOR_COLUMNS if frame[column].notna().any()]
    invalid_ranges = pd.DataFrame(
        {
            column: ~frame[column].between(lower, upper)
            for column, (lower, upper) in PLAUSIBLE_RANGES.items()
            if column in observed_columns
        },
        index=frame.index,
    )
    frame["sensor_fault"] = (
        frame[observed_columns].isna().any(axis=1)
        | frame["timestamp"].isna()
        | (invalid_ranges.any(axis=1) if not invalid_ranges.empty else False)
    )

    feed = frame["feed_lpm"]
    flow_columns = ["feed_lpm", "permeate_lpm", "reject_lpm"]
    have_flow_data = all(frame[column].notna().any() for column in flow_columns)
    valid_feed = feed.gt(0) if have_flow_data else pd.Series(False, index=frame.index)
    frame["recovery_pct"] = (frame["permeate_lpm"] / feed * 100).where(valid_feed)
    frame["reject_pct"] = (frame["reject_lpm"] / feed * 100).where(valid_feed)
    frame["mass_balance_error_pct"] = (
        (feed - frame["permeate_lpm"] - frame["reject_lpm"]).abs() / feed * 100
    ).where(valid_feed)
    have_tds_data = frame["raw_tds_ppm"].notna().any() and frame["permeate_tds_ppm"].notna().any()
    frame["tds_rejection_pct"] = (
        (frame["raw_tds_ppm"] - frame["permeate_tds_ppm"])
        / frame["raw_tds_ppm"]
        * 100
    ).where(frame["raw_tds_ppm"].gt(0)) if have_tds_data else np.nan

    if have_flow_data:
        frame["flow_fault"] = (
            ~valid_feed
            | frame[flow_columns].isna().any(axis=1)
            | frame[["permeate_lpm", "reject_lpm"]].lt(0).any(axis=1)
        )
        frame["mass_balance_fault"] = frame["mass_balance_error_pct"].gt(5)
    else:
        frame["flow_fault"] = False
        frame["mass_balance_fault"] = False
    frame["pressure_trip"] = (
        frame["pressure_bar"].gt(4.5)
        if "pressure_bar" in observed_columns
        else False
    )
    frame["active_alarm"] = (
        frame["sensor_fault"]
        | frame["flow_fault"]
        | frame["pressure_trip"]
        | frame["mass_balance_fault"]
    )
    return frame


DEMO_SCENARIOS = ("Nominal", "Pressure trip", "Sensor fault", "Flow imbalance")


def make_demo_telemetry(
    n_samples: int = 48,
    seed: int = 42,
    scenario: str = "Nominal",
) -> pd.DataFrame:
    """Create deterministic, explicitly simulated telemetry for UI demonstrations."""
    if n_samples < 2:
        raise ValueError("At least two samples are required for trend charts.")
    if scenario not in DEMO_SCENARIOS:
        raise ValueError(f"Unknown demo scenario: {scenario}")

    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n_samples, freq="h")
    feed = 1.2 + rng.normal(0, 0.015, n_samples)
    recovery = np.linspace(0.61, 0.64, n_samples)
    permeate = feed * recovery
    reject = feed - permeate
    demo_data = pd.DataFrame(
        {
            "timestamp": timestamps,
            "ph": 7.1 + rng.normal(0, 0.08, n_samples),
            "raw_tds_ppm": 500 + rng.normal(0, 12, n_samples),
            "permeate_tds_ppm": 28 + rng.normal(0, 3, n_samples),
            "turbidity_ntu": np.clip(2.4 + rng.normal(0, 0.2, n_samples), 0, None),
            "uv254_abs": np.clip(0.12 + rng.normal(0, 0.008, n_samples), 0, None),
            "pressure_bar": np.linspace(2.6, 3.1, n_samples) + rng.normal(0, 0.03, n_samples),
            "feed_lpm": feed,
            "permeate_lpm": permeate,
            "reject_lpm": reject,
            "calcium_mg_l": 24 + rng.normal(0, 1, n_samples),
            "magnesium_mg_l": 16 + rng.normal(0, 0.8, n_samples),
            "filter_operating_l": np.linspace(0, 480, n_samples),
        }
    )
    if scenario == "Pressure trip":
        demo_data.loc[demo_data.index[-1], "pressure_bar"] = 4.8
    elif scenario == "Sensor fault":
        demo_data.loc[demo_data.index[-1], "ph"] = 15.0
    elif scenario == "Flow imbalance":
        demo_data.loc[demo_data.index[-1], "reject_lpm"] += 0.15
    return demo_data