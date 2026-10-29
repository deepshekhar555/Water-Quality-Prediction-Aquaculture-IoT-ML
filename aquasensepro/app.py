from pathlib import Path

import pandas as pd
import streamlit as st

from aquasensepro.aquaculture import (
    FEATURE_COLUMNS,
    available_observed_targets,
    evaluate_models,
    normalize_measurements,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "major project Final excel no.1.xlsx"


def read_measurements(
    source: object,
    filename: str,
    impute_missing: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    raw = pd.read_csv(source) if filename.casefold().endswith(".csv") else pd.read_excel(source)
    return normalize_measurements(raw, impute_missing=impute_missing)


st.set_page_config(page_title="PondScope | Field Monitor", page_icon="◉", layout="wide")
st.markdown(
    """
    <style>
      :root { --ink:#18383a; --muted:#607779; --paper:#f3f7f5; --line:#d6e2dd; --accent:#bd5d43; --leaf:#567866; }
      .stApp { background:var(--paper); color:var(--ink); }
      [data-testid="stSidebar"] { background:#e6efeb; border-right:1px solid var(--line); }
      h1,h2,h3 { color:var(--ink); font-family:"Aptos Display","Trebuchet MS",sans-serif; }
      h1 { font-size:2.05rem; font-weight:680; }
      [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:5px; padding:13px 15px; }
      [data-testid="stMetricLabel"] { color:var(--muted); }
      .eyebrow { color:var(--accent); font-size:.73rem; font-weight:750; letter-spacing:.08em; }
      .muted { color:var(--muted); font-size:.91rem; }
      .source-banner { background:#edf3ef; border-left:4px solid var(--leaf); padding:10px 14px; color:#274b3e; border-radius:3px; }
      .estimate-banner { background:#fff4db; border-left:4px solid #d9902f; padding:10px 14px; color:#614918; border-radius:3px; }
      @media (max-width: 700px) { h1 { font-size:1.55rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("<p class='eyebrow'>FIELD DATA</p>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload pond samples", type=["csv", "xlsx", "xls"])
    data_source = uploaded_file if uploaded_file is not None else DEFAULT_DATA
    filename = uploaded_file.name if uploaded_file is not None else DEFAULT_DATA.name
    st.caption(f"Source: {filename}")
    impute_missing = st.toggle("Impute partial sample groups", value=False)
    st.divider()
    st.caption("KNN imputation is optional and marked in the data table. Required fields: sample ID, pH, temperature, turbidity.")

try:
    measurements, quality_summary = read_measurements(data_source, filename, impute_missing)
except FileNotFoundError:
    st.error(f"Default workbook not found: {DEFAULT_DATA.name}")
    st.stop()
except Exception as error:
    st.error(f"Could not load sample data: {error}")
    st.stop()

if measurements.empty:
    st.warning("No complete, in-range sample rows were found.")
    st.stop()

sample_min = int(measurements["Sample"].min())
sample_max = int(measurements["Sample"].max())
if sample_min < sample_max:
    with st.sidebar:
        sample_window = st.slider(
            "Sample window",
            min_value=sample_min,
            max_value=sample_max,
            value=(sample_min, sample_max),
        )
else:
    sample_window = (sample_min, sample_max)

visible = measurements[measurements["Sample"].between(*sample_window)].copy()
observed_do = (
    "Dissolved oxygen observed (mg/L)" in visible
    and visible["Dissolved oxygen observed (mg/L)"].notna().any()
)
do_column = "Dissolved oxygen for display (mg/L)"
do_label = "Observed / estimated dissolved oxygen"

st.markdown("<p class='eyebrow'>AQUACULTURE / POND MONITORING</p>", unsafe_allow_html=True)
st.title("Pond water, in context")
st.markdown(
    f"<p class='muted'>{len(visible)} selected samples · {len(measurements)} valid samples in source</p>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<div class='source-banner'><b>DATA SOURCE</b> &nbsp; {filename} · offline sample data; no live sensor connection is configured.</div>",
    unsafe_allow_html=True,
)
if not observed_do:
    st.markdown(
        "<div class='estimate-banner'><b>DO IS ESTIMATED</b> &nbsp; Oxygen values use an empirical estimate, not a DO sensor or lab titration.</div>",
        unsafe_allow_html=True,
    )

metric_columns = st.columns(4)
metric_columns[0].metric("Valid samples", len(visible))
metric_columns[1].metric("Mean pH", f"{visible['pH'].mean():.2f}")
metric_columns[2].metric("Mean temperature", f"{visible['Temperature (°C)'].mean():.2f} °C")
metric_columns[3].metric("Mean turbidity", f"{visible['Turbidity (NTU)'].mean():.2f} NTU")
st.caption(
    f"Source workbook: {quality_summary['source_rows']} logger rows, including "
    f"{quality_summary['unkeyed_rows']} readings without a sample ID; the display uses grouped sample summaries."
)

monitor_tab, models_tab, quality_tab = st.tabs(["Monitoring", "Prediction analysis", "Data quality"])

with monitor_tab:
    chart_columns = st.columns(2)
    chart_specs = [
        ("pH across samples", "pH"),
        ("Temperature across samples", "Temperature (°C)"),
        ("Turbidity across samples", "Turbidity (NTU)"),
        (do_label, do_column),
    ]
    for column, (title, metric) in zip(chart_columns * 2, chart_specs):
        with column:
            st.markdown(f"**{title}**")
            st.line_chart(visible, x="Sample", y=metric, height=235)

    st.markdown("**Estimated water-quality score**")
    st.line_chart(visible, x="Sample", y="Water quality score estimate", height=220)
    st.caption("Composite estimate from the available measurements; it is not a regulatory water-quality index.")
    st.markdown(
        "<div class='estimate-banner'><b>INTERPRET WITH CARE</b> &nbsp; Estimated dissolved oxygen is not a measured reading or a safety certification.</div>",
        unsafe_allow_html=True,
    )

with models_tab:
    st.subheader("Model comparison")
    available_targets = available_observed_targets(visible)
    target_options = available_targets or ["Water quality score estimate"]
    selected_target = st.selectbox("Prediction target", target_options)
    if selected_target == "Dissolved oxygen observed (mg/L)":
        st.info("Target source: independently measured dissolved oxygen.")
    elif selected_target == "Water quality observed":
        st.info("Target source: independently supplied water-quality labels.")
    elif selected_target == "Water quality from observed DO":
        st.warning("Target uses measured DO inside the composite score; it is not an independent water-quality label.")
    else:
        st.warning("No observed target is available. This evaluates reconstruction of the empirical score, not future conditions.")
    try:
        scores, predictions = evaluate_models(visible, selected_target)
    except ValueError as error:
        st.info(str(error))
    else:
        st.dataframe(scores.round(4), hide_index=True, width="stretch")
        selected_model = st.selectbox("Prediction overlay", ["Linear regression", "Random forest"])
        st.scatter_chart(predictions, x="Target", y=selected_model, height=280)
        st.caption(f"Validation: {scores['Validation'].iloc[0]}. Scores are not proof of fish survival or water safety.")
        importance_columns = [f"{feature} ΔMAE" for feature in FEATURE_COLUMNS]
        importance = scores.set_index("Model")[importance_columns].T
        importance.index = FEATURE_COLUMNS
        st.markdown("**Held-out feature importance**")
        st.bar_chart(importance, height=240)
        st.caption("Permutation importance is the increase in held-out MAE after shuffling a feature; it is not causal evidence.")

    st.markdown("**Feature relationships**")
    st.dataframe(visible[FEATURE_COLUMNS].corr().round(3), width="stretch")

with quality_tab:
    st.subheader("Sample audit")
    audit_columns = st.columns(4)
    audit_columns[0].metric("Input rows", quality_summary["source_rows"])
    audit_columns[1].metric("Unkeyed readings", quality_summary["unkeyed_rows"])
    audit_columns[2].metric("Incomplete groups", quality_summary["incomplete_rows"])
    audit_columns[3].metric("Imputed groups", quality_summary["imputed_rows"])
    st.metric("Out-of-range sample groups", quality_summary["out_of_range_rows"])
    st.metric("Duplicate sample IDs", quality_summary["duplicate_sample_ids"])
    st.caption(f"IQR review flags: {quality_summary['iqr_review_rows']}. Flags are for manual review, not pond-safety or fish-health diagnoses.")
    flagged = visible[visible["IQR review flag"]]
    if flagged.empty:
        st.success("No IQR review flags in the selected sample window.")
    else:
        st.dataframe(flagged, hide_index=True, width="stretch")
    st.download_button(
        "Download selected samples CSV",
        data=visible.to_csv(index=False),
        file_name="pond-water-samples.csv",
        mime="text/csv",
        icon=":material/download:",
    )
    st.dataframe(visible, hide_index=True, width="stretch")

st.caption(
    "Equation-derived DO and composite scores are estimates; only a calibrated DO probe or laboratory test can provide observed DO."
)
