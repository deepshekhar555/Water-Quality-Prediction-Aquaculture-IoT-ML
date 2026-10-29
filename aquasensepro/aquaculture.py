from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import KNNImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, KFold, TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline


FEATURE_COLUMNS = ["pH", "Temperature (°C)", "Turbidity (NTU)"]
MEASUREMENT_COLUMNS = ["Sample", *FEATURE_COLUMNS]
OUTLIER_COLUMNS = FEATURE_COLUMNS + [
    "Dissolved oxygen estimate (mg/L)",
    "Dissolved oxygen observed (mg/L)",
]

ALIASES = {
    "Sample": ("sampleid", "sampleno", "samplenumber", "sample"),
    "pH": ("avgph", "averageph", "ph"),
    "Temperature (°C)": ("avgtempc", "temperaturec", "c", "tempc", "temperature"),
    "Turbidity (NTU)": ("turbidityntu", "ntu", "turbidity"),
    "Pond ID": ("pondid", "pond", "siteid", "locationid"),
    "Timestamp": ("timestampms", "timems", "timestamp", "datetime", "date"),
    "Dissolved oxygen observed (mg/L)": (
        "dissolvedoxygenmgl",
        "dissolvedoxygen",
        "do(mgl)",
        "do",
    ),
    "Water quality observed": ("waterquality", "waterqualityobserved"),
}


def _column_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())


def normalize_measurements(
    raw: pd.DataFrame,
    impute_missing: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Normalize common workbook/CSV headers and derive transparent study features."""
    source = raw.copy()
    source_rows = len(source)
    columns_by_key = {_column_key(column): column for column in source.columns}
    rename: dict[Any, str] = {}
    for canonical, aliases in ALIASES.items():
        match = next((columns_by_key[alias] for alias in aliases if alias in columns_by_key), None)
        if match is not None:
            rename[match] = canonical

    frame = source.rename(columns=rename)
    missing_columns = [column for column in MEASUREMENT_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    for column in MEASUREMENT_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("Dissolved oxygen observed (mg/L)", "Water quality observed"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "Timestamp" in frame:
        numeric_timestamp = pd.to_numeric(frame["Timestamp"], errors="coerce")
        if numeric_timestamp.notna().sum() >= frame["Timestamp"].notna().sum() * 0.8:
            frame["Timestamp"] = numeric_timestamp
        else:
            frame["Timestamp"] = pd.to_datetime(frame["Timestamp"], errors="coerce", utc=True)

    has_sample_id = frame["Sample"].notna()
    complete_values = frame[FEATURE_COLUMNS].notna().all(axis=1)
    incomplete_rows = int((has_sample_id & ~complete_values).sum())
    unkeyed_rows = int((~has_sample_id).sum())
    complete_mask = has_sample_id & complete_values
    imputed_rows = 0
    if impute_missing and incomplete_rows:
        complete_reference_count = int((has_sample_id & complete_values).sum())
        if complete_reference_count < 5:
            raise ValueError("KNN imputation requires at least five complete sample groups.")
        candidates = frame.loc[has_sample_id].copy()
        missing_mask = candidates[FEATURE_COLUMNS].isna()
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(candidates[FEATURE_COLUMNS])
        imputer = KNNImputer(n_neighbors=min(5, complete_reference_count))
        filled_features = scaler.inverse_transform(imputer.fit_transform(scaled_features))
        candidates[FEATURE_COLUMNS] = filled_features
        candidates["Imputed fields"] = missing_mask.apply(
            lambda row: ", ".join(row.index[row].tolist()), axis=1
        )
        imputed_rows = int(missing_mask.any(axis=1).sum())
        complete = candidates
    else:
        complete = frame.loc[complete_mask].copy()
        complete["Imputed fields"] = ""

    in_range_mask = (
        complete["Sample"].gt(0)
        & complete["pH"].between(0, 14)
        & complete["Temperature (°C)"].between(-5, 50)
        & complete["Turbidity (NTU)"].between(0, 1000)
    )
    valid = complete.loc[in_range_mask].sort_values("Sample").copy()

    valid["Dissolved oxygen estimate (mg/L)"] = (
        0.14
        * np.power(valid["pH"], 0.01)
        * np.exp(0.2 * valid["Temperature (°C)"])
        * 0.15
        * np.power(valid["Turbidity (NTU)"], 0.01)
    )
    observed_do_column = "Dissolved oxygen observed (mg/L)"
    if observed_do_column in valid:
        observed_values = valid[observed_do_column]
        valid["Dissolved oxygen for display (mg/L)"] = observed_values.combine_first(
            valid["Dissolved oxygen estimate (mg/L)"]
        )
        valid["Dissolved oxygen basis"] = np.where(
            observed_values.notna(), "Observed", "Empirical estimate"
        )
    else:
        valid["Dissolved oxygen for display (mg/L)"] = valid[
            "Dissolved oxygen estimate (mg/L)"
        ]
        valid["Dissolved oxygen basis"] = "Empirical estimate"
    valid["Water quality score estimate"] = (
        0.2 * valid["Temperature (°C)"]
        + 0.1 * valid["pH"]
        + 0.15 * valid["Dissolved oxygen estimate (mg/L)"]
        - 0.05 * valid["Turbidity (NTU)"]
    )
    if "Dissolved oxygen observed (mg/L)" in valid:
        valid["Water quality from observed DO"] = (
            0.2 * valid["Temperature (°C)"]
            + 0.1 * valid["pH"]
            + 0.15 * valid["Dissolved oxygen observed (mg/L)"]
            - 0.05 * valid["Turbidity (NTU)"]
        )

    outlier_mask = pd.Series(False, index=valid.index)
    for column in OUTLIER_COLUMNS:
        if column not in valid:
            continue
        first_quartile = valid[column].quantile(0.25)
        third_quartile = valid[column].quantile(0.75)
        interquartile_range = third_quartile - first_quartile
        if interquartile_range > 0:
            outlier_mask |= (valid[column] < first_quartile - 1.5 * interquartile_range) | (
                valid[column] > third_quartile + 1.5 * interquartile_range
            )
    valid["IQR review flag"] = outlier_mask

    summary = {
        "source_rows": source_rows,
        "incomplete_rows": incomplete_rows,
        "unkeyed_rows": unkeyed_rows,
        "imputed_rows": imputed_rows,
        "out_of_range_rows": int(len(complete) - len(valid)),
        "duplicate_sample_ids": int(valid["Sample"].duplicated().sum()),
        "iqr_review_rows": int(outlier_mask.sum()),
        "valid_rows": len(valid),
    }
    return valid.reset_index(drop=True), summary


def available_observed_targets(measurements: pd.DataFrame) -> list[str]:
    return [
        target
        for target in (
            "Dissolved oxygen observed (mg/L)",
            "Water quality observed",
            "Water quality from observed DO",
        )
        if target in measurements and measurements[target].notna().sum() >= 10
    ]


def evaluate_models(
    measurements: pd.DataFrame,
    target_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare simple regressors with metadata-aware holdout validation."""
    evaluation_data = measurements.dropna(subset=[target_column])
    if len(evaluation_data) < 10:
        raise ValueError("At least 10 valid samples are needed for five-fold evaluation.")

    if "Pond ID" in evaluation_data and evaluation_data["Pond ID"].nunique() >= 2:
        groups = evaluation_data["Pond ID"].fillna("unknown").astype(str)
        n_splits = min(5, groups.nunique())
        fold_splits = list(GroupKFold(n_splits=n_splits).split(evaluation_data, groups=groups))
        validation_method = f"{n_splits}-fold pond-held-out"
    elif "Timestamp" in evaluation_data and evaluation_data["Timestamp"].notna().sum() >= 10:
        ordered = evaluation_data.sort_values("Timestamp")
        evaluation_data = ordered
        n_splits = min(5, len(evaluation_data) - 1)
        fold_splits = list(TimeSeriesSplit(n_splits=n_splits).split(evaluation_data))
        validation_method = "chronological expanding-window"
    else:
        fold_splits = list(KFold(n_splits=5, shuffle=True, random_state=42).split(evaluation_data))
        validation_method = "5-fold shuffled sample split"

    features = evaluation_data[FEATURE_COLUMNS].copy()
    imputation_enabled = "Imputed fields" in evaluation_data and evaluation_data[
        "Imputed fields"
    ].fillna("").ne("").any()
    if imputation_enabled:
        for row_index, imputed_fields in evaluation_data["Imputed fields"].items():
            for feature in str(imputed_fields).split(", "):
                if feature in FEATURE_COLUMNS:
                    features.loc[row_index, feature] = np.nan
    target = evaluation_data[target_column]
    models = {
        "Linear regression": LinearRegression(),
        "Random forest": RandomForestRegressor(n_estimators=200, random_state=42),
    }
    scores = []
    prediction_frame = evaluation_data[["Sample"]].copy()
    prediction_frame["Target"] = target
    for name, model in models.items():
        predicted = np.full(len(evaluation_data), np.nan)
        fold_importances = []
        for train_indices, test_indices in fold_splits:
            fold_model = (
                make_pipeline(
                    StandardScaler(),
                    KNNImputer(n_neighbors=min(5, len(train_indices))),
                    model,
                )
                if imputation_enabled
                else model
            )
            fold_model.fit(features.iloc[train_indices], target.iloc[train_indices])
            predicted[test_indices] = fold_model.predict(features.iloc[test_indices])
            importance = permutation_importance(
                fold_model,
                features.iloc[test_indices],
                target.iloc[test_indices],
                n_repeats=3,
                random_state=42,
                scoring="neg_mean_absolute_error",
            )
            fold_importances.append(importance.importances_mean)
        prediction_frame[name] = predicted
        scored = np.isfinite(predicted)
        mean_importance = np.mean(fold_importances, axis=0)
        scores.append(
            {
                "Model": name,
                "Evaluation target": target_column,
                "Validation": validation_method,
                "Evaluated samples": int(scored.sum()),
                "MAE": mean_absolute_error(target.iloc[scored], predicted[scored]),
                "RMSE": np.sqrt(mean_squared_error(target.iloc[scored], predicted[scored])),
                "R²": r2_score(target.iloc[scored], predicted[scored]),
                **{
                    f"{feature} ΔMAE": importance
                    for feature, importance in zip(FEATURE_COLUMNS, mean_importance)
                },
            }
        )
    return pd.DataFrame(scores), prediction_frame.loc[prediction_frame["Linear regression"].notna()].reset_index(drop=True)