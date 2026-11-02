from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from aquasensepro.purifier_monitoring import (
    DEMO_SCENARIOS,
    TELEMETRY_COLUMNS,
    make_demo_telemetry,
    prepare_telemetry,
)
from aquasensepro.rul_pipeline import XGBoostRULPipeline, generate_synthetic_rul_data
from aquasensepro.serial_telemetry import SerialTelemetryReader, available_serial_ports


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TELEMETRY_PATH = PROJECT_ROOT / "purifier_telemetry_demo_simulated.csv"


def open_project_sample() -> None:
    st.session_state["purifier_data_mode"] = "Upload CSV"
    st.session_state["load_bundled_sample"] = True


st.set_page_config(page_title="AquaSense Pro | Purifier Monitor", page_icon="◉", layout="wide")
st.markdown(
    """
    <style>
      :root { --ink:#17323a; --muted:#60767a; --paper:#f3f7f5; --line:#d5e0dc; --teal:#087f82; --gold:#bd761a; --red:#b74435; }
      .stApp { background:var(--paper); color:var(--ink); }
      [data-testid="stSidebar"] { background:#e7efeb; border-right:1px solid var(--line); }
      h1,h2,h3 { color:var(--ink); font-family:"Aptos Display","Trebuchet MS",sans-serif; }
      h1 { font-size:2rem; font-weight:700; }
      [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:4px; padding:12px 14px; }
    [data-testid="stMetricLabel"] { white-space:normal; line-height:1.2; }
      .eyebrow { color:var(--teal); font-size:.75rem; font-weight:750; letter-spacing:.08em; }
      .notice { padding:10px 13px; border-left:4px solid var(--gold); background:#fff4df; color:#614918; }
      .ok { padding:10px 13px; border-left:4px solid var(--teal); background:#e8f4f1; color:#1e514a; }
      @media (max-width: 700px) { h1 { font-size:1.55rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

if "serial_telemetry_reader" not in st.session_state:
    st.session_state.serial_telemetry_reader = SerialTelemetryReader()
serial_reader = st.session_state.serial_telemetry_reader
data_mode = st.segmented_control(
    "Data source",
    ["Live USB", "Upload CSV", "Simulation"],
    default="Live USB",
    key="purifier_data_mode",
    width="stretch",
)
uploaded_file = None
demo_scenario = "Nominal"
calcium_target = 30.0
magnesium_target = 20.0
capacity_l = 0.0

if data_mode == "Upload CSV":
    st.subheader("Upload telemetry")
    uploaded_file = st.file_uploader("Choose a telemetry CSV", type=["csv"])
    upload_actions = st.columns(2)
    with upload_actions[0]:
        st.download_button(
            "Empty CSV template",
            data=pd.DataFrame(columns=["timestamp", *TELEMETRY_COLUMNS[1:]]).to_csv(index=False),
            file_name="purifier_telemetry_template.csv",
            mime="text/csv",
            width="stretch",
        )
    with upload_actions[1]:
        st.download_button(
            "Sample CSV · simulated",
            data=SAMPLE_TELEMETRY_PATH.read_bytes(),
            file_name=SAMPLE_TELEMETRY_PATH.name,
            mime="text/csv",
            width="stretch",
        )
    if uploaded_file is None and st.button("Load project sample into dashboard", type="primary"):
        st.session_state["load_bundled_sample"] = True
        st.rerun()
elif data_mode == "Simulation":
    demo_scenario = st.selectbox("Demo scenario", DEMO_SCENARIOS)

with st.sidebar:
    st.markdown("<p class='eyebrow'>AQUASENSE PRO / REGEN-X</p>", unsafe_allow_html=True)
    if data_mode != "Live USB":
        with st.expander("Analysis settings"):
            calcium_target = st.number_input("Calcium target (mg/L)", min_value=0.0, value=30.0, step=1.0)
            magnesium_target = st.number_input("Magnesium target (mg/L)", min_value=0.0, value=20.0, step=1.0)
            capacity_l = st.number_input("Filter rated capacity (L)", min_value=0.0, value=0.0, step=100.0)
    st.caption("Software alarms do not actuate physical valves or dosing pumps.")

if data_mode == "Live USB":
    serial_ports = available_serial_ports()
    if serial_ports:
        port_column, baud_column, action_column = st.columns([2, 1, 1])
        with port_column:
            selected_port = st.selectbox(
                "USB serial port",
                [port for port, _ in serial_ports],
                format_func=lambda port: next(
                    f"{name} · {description}" for name, description in serial_ports if name == port
                ),
            )
        with baud_column:
            baud_rate = st.selectbox("Baud rate", [9600, 115200], index=0)
        with action_column:
            st.write("")
            if serial_reader.connected:
                if st.button("Disconnect ESP32", width="stretch"):
                    serial_reader.disconnect()
                    st.rerun()
            elif st.button("Connect ESP32", type="primary", width="stretch"):
                try:
                    serial_reader.connect(selected_port, baud_rate)
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not open {selected_port}: {error}")
    else:
        status_column, refresh_column = st.columns([3, 1])
        with status_column:
            st.info("No USB serial device detected. Connect the board, then refresh ports.")
        with refresh_column:
            if st.button("Refresh ports", width="stretch"):
                st.rerun()
    st.caption("Expected firmware stream: sample_id,timestamp_ms,pH,temperature_c,turbidity_ntu · 9600 baud")
    st.caption("Only channels emitted by the connected sketch appear as measurements.")

if data_mode == "Live USB":
    if not serial_reader.connected:
        st.title("Waiting for ESP32 connection")
        st.markdown(
            "<div class='notice'><b>No device connected.</b> Live mode never substitutes simulated values. Connect the board and refresh serial ports, or use the bundled sample to preview the charts.</div>",
            unsafe_allow_html=True,
        )
        st.subheader("Channels in the included sketch")
        st.dataframe(
            pd.DataFrame(
                [
                    ("pH", "Emitted over USB · calibration needs verification"),
                    ("Temperature", "Emitted over USB"),
                    ("Turbidity", "Emitted as firmware-mapped units · calibration needs verification"),
                    ("TDS / UV254 / pressure / flow / minerals", "Not emitted by this sketch"),
                ],
                columns=["Channel", "Availability"],
            ),
            hide_index=True,
            width="stretch",
        )
        st.button("Preview bundled sample dashboard", on_click=open_project_sample, type="primary")
        st.stop()

    @st.fragment(run_every="1s")
    def show_live_telemetry() -> None:
        serial_reader.poll()
        if serial_reader.error:
            st.error(f"Serial connection stopped: {serial_reader.error}")
            return
        if not serial_reader.rows:
            st.info("Connected; waiting for the first CSV reading from the device.")
            return

        raw_serial = pd.DataFrame(list(serial_reader.rows))
        try:
            telemetry = prepare_telemetry(raw_serial)
        except ValueError as error:
            st.error(f"Could not normalize ESP32 data: {error}")
            return

        latest = telemetry.iloc[-1]
        st.markdown("<p class='eyebrow'>LIVE USB TELEMETRY · READ ONLY</p>", unsafe_allow_html=True)
        st.title("Sensor bench monitor")
        st.caption(f"Port {serial_reader.port} · {len(telemetry)} buffered readings · {serial_reader.decoder.invalid_lines} malformed lines skipped")
        st.markdown(
            "<div class='notice'><b>Calibration note:</b> the current sketch uses example pH calibration and maps turbidity ADC to 0–100. Verify both against reference instruments before using these values as calibrated measurements.</div>",
            unsafe_allow_html=True,
        )

        def display_value(value: object, unit: str) -> str:
            return "Unavailable" if pd.isna(value) else f"{float(value):.2f} {unit}"

        sensor_metrics = st.columns(3)
        sensor_metrics[0].metric("pH · sketch", display_value(latest["ph"], ""))
        sensor_metrics[1].metric("Temperature", display_value(latest["temperature_c"], "°C"))
        sensor_metrics[2].metric("Turbidity · sketch", display_value(latest["turbidity_ntu"], "raw mapped units"))
        last_received = pd.to_datetime(raw_serial.iloc[-1]["received_at"], utc=True)
        sample_age_seconds = (pd.Timestamp.now(tz="UTC") - last_received).total_seconds()
        if sample_age_seconds > 5:
            st.warning(f"No new serial row for {sample_age_seconds:.0f} seconds; latest reading may be stale.")
        if bool(latest["sensor_fault"]):
            st.error("Latest live row contains a missing or out-of-range sensor value.")
        else:
            st.success("Latest received sensor values are within configured software ranges.")
        st.caption("TDS, UV254, pressure, flow, calcium, and magnesium are not emitted by the current sketch and are intentionally unavailable.")

        chart_columns = st.columns(2)
        for column, metric, title in zip(
            chart_columns * 2,
            ("ph", "temperature_c", "turbidity_ntu"),
            ("pH", "Temperature (°C)", "Turbidity (firmware-mapped units)"),
        ):
            if telemetry[metric].notna().any():
                with column:
                    st.markdown(f"**{title}**")
                    st.line_chart(telemetry.set_index("timestamp")[[metric]], height=220)

        st.dataframe(raw_serial.tail(20), hide_index=True, width="stretch")
        st.download_button(
            "Download received serial readings",
            data=raw_serial.to_csv(index=False),
            file_name="esp32_sensor_readings.csv",
            mime="text/csv",
        )

    show_live_telemetry()
    st.stop()

if data_mode == "Upload CSV":
    load_bundled_sample = st.session_state.pop("load_bundled_sample", False)
    if uploaded_file is not None:
        try:
            raw_data = pd.read_csv(uploaded_file)
            if "data_origin" in raw_data and raw_data["data_origin"].astype(str).str.contains("SIMULATED", case=False).any():
                source_label = f"SIMULATION CSV · {uploaded_file.name} · generated example, not measured data"
            else:
                source_label = f"Uploaded CSV · {uploaded_file.name} · physical origin not verified"
        except Exception as error:
            st.error(f"Could not read the CSV: {error}")
            st.stop()
    elif load_bundled_sample:
        raw_data = pd.read_csv(SAMPLE_TELEMETRY_PATH)
        source_label = "SIMULATION CSV · bundled 12-row example · not measured data"
    elif st.session_state.pop("load_bundled_sample", False):
        raw_data = pd.read_csv(SAMPLE_TELEMETRY_PATH)
        source_label = "SIMULATION CSV · bundled 12-row example · not measured data"
    else:
        st.info("Choose a CSV with at least one data row, or load the bundled sample to preview the dashboard.")
        st.stop()
else:
    raw_data = make_demo_telemetry(scenario=demo_scenario)
    source_label = f"SIMULATION · {demo_scenario} · generated data, not physical sensor readings"

if raw_data.empty:
    st.error("This CSV contains headers but no telemetry rows. Use the bundled sample or add measurement rows before uploading.")
    st.stop()

try:
    telemetry = prepare_telemetry(raw_data)
except ValueError as error:
    st.error(str(error))
    st.caption("Required columns: " + ", ".join(TELEMETRY_COLUMNS))
    st.stop()

st.markdown("<p class='eyebrow'>ROUND 2 PROTOTYPE MONITOR</p>", unsafe_allow_html=True)
st.title("Purifier process monitor")
st.caption(source_label)
st.markdown(
    "<div class='notice'><b>Prototype status:</b> This software does not establish that physical sensors, RO recovery, mineral dosing, or safety interlocks are connected or validated. Demo mode is simulated.</div>",
    unsafe_allow_html=True,
)

latest = telemetry.iloc[-1]
alarm_rows = int(telemetry["active_alarm"].sum())


def metric_value(value: object, precision: int = 1, unit: str = "") -> str:
    if pd.isna(value):
        return "Unavailable"
    return f"{float(value):.{precision}f}{unit}"


def show_chart(title: str, columns: dict[str, str], height: int = 240) -> bool:
    chart_data = telemetry.set_index("timestamp")[
        [column for column in columns if telemetry[column].notna().any()]
    ].rename(columns=columns)
    if chart_data.empty or chart_data.shape[1] == 0:
        return False
    st.markdown(f"**{title}**")
    st.line_chart(chart_data, height=height)
    return True


metrics = st.columns(2)
metrics[0].metric("Pressure", metric_value(latest["pressure_bar"], 2, " bar"))
metrics[1].metric("TDS rejection", metric_value(latest["tds_rejection_pct"], 1, "%"))
metrics = st.columns(2)
metrics[0].metric("RO recovery", metric_value(latest["recovery_pct"], 1, "%"))
metrics[1].metric("Software alarm rows", f"{alarm_rows}/{len(telemetry)}")

if bool(latest["active_alarm"]):
    active_reasons = []
    if bool(latest["pressure_trip"]):
        active_reasons.append("pressure over 4.5 bar")
    if bool(latest["sensor_fault"]):
        active_reasons.append("missing or out-of-range sensor value")
    if bool(latest["flow_fault"]):
        active_reasons.append("invalid flow record")
    if bool(latest["mass_balance_fault"]):
        active_reasons.append("flow mass-balance deviation over 5%")
    st.error("Latest-row software alarm: " + "; ".join(active_reasons) + ". No physical isolation is performed.")
else:
    st.markdown("<div class='ok'><b>Latest record:</b> no configured software alarm. Hardware safety remains unverified.</div>", unsafe_allow_html=True)

sensor_tab, process_tab, filter_tab = st.tabs(["Sensors", "RO / ReGen-X", "Filter & safety"])

with sensor_tab:
    sensor_columns = st.columns(2)
    with sensor_columns[0]:
        if not show_chart("pH", {"ph": "pH"}, height=260):
            st.caption("pH is not available in this data source.")
    with sensor_columns[1]:
        if not show_chart(
            "TDS · feed vs permeate (ppm)",
            {"raw_tds_ppm": "Feed TDS (ppm)", "permeate_tds_ppm": "Permeate TDS (ppm)"},
            height=260,
        ):
            st.caption("TDS channels are not available in this data source.")
    sensor_columns = st.columns(2)
    with sensor_columns[0]:
        if not show_chart("Turbidity (NTU or firmware-mapped units)", {"turbidity_ntu": "Turbidity"}, height=220):
            st.caption("Turbidity is not available in this data source.")
    with sensor_columns[1]:
        if not show_chart("UV254 absorbance (AU)", {"uv254_abs": "UV254 (AU)"}, height=220):
            st.caption("UV254 is not available in this data source.")
    if not show_chart("Feed pressure (bar)", {"pressure_bar": "Pressure (bar)"}, height=220):
        st.caption("Pressure is not available in this data source.")
    st.caption("UV254 is shown as a sensor channel only; no organic-contaminant or drinking-water safety classification is inferred.")

with process_tab:
    if all(telemetry[column].notna().any() for column in ("feed_lpm", "permeate_lpm", "reject_lpm")):
        process_metrics = st.columns(4)
        process_metrics[0].metric("Feed (L/min)", metric_value(latest["feed_lpm"], 2))
        process_metrics[1].metric("Permeate (L/min)", metric_value(latest["permeate_lpm"], 2))
        process_metrics[2].metric("Reject (L/min)", metric_value(latest["reject_lpm"], 2))
        process_metrics[3].metric("Mass-balance error", metric_value(latest["mass_balance_error_pct"], 2, "%"))
        show_chart(
            "Feed, permeate, and reject flow (L/min)",
            {"feed_lpm": "Feed", "permeate_lpm": "Permeate", "reject_lpm": "Reject"},
            height=260,
        )
    else:
        st.info("Feed, permeate, and reject flow are not all available; process balance is not calculated.")
    if telemetry["calcium_mg_l"].notna().any() or telemetry["magnesium_mg_l"].notna().any():
        show_chart(
            "Mineral concentrations (mg/L)",
            {"calcium_mg_l": "Calcium", "magnesium_mg_l": "Magnesium"},
            height=230,
        )
        calcium_gap = calcium_target - float(latest["calcium_mg_l"])
        magnesium_gap = magnesium_target - float(latest["magnesium_mg_l"])
        st.write(
            f"Latest difference from targets: calcium {calcium_gap:+.1f} mg/L; "
            f"magnesium {magnesium_gap:+.1f} mg/L. These are comparisons, not dosing commands."
        )
    else:
        st.info("Calcium and magnesium channels are not available in this data source.")
    st.caption("Electrodialysis recovery and dosing are not controlled by this dashboard.")

with filter_tab:
    has_filter_volume = telemetry["filter_operating_l"].notna().any()
    if has_filter_volume:
        show_chart("Logged filter volume (L)", {"filter_operating_l": "Filter volume (L)"}, height=260)
    if has_filter_volume and capacity_l > 0:
        current_volume = float(latest["filter_operating_l"])
        capacity_used = min(100.0, current_volume / capacity_l * 100)
        st.metric("Rated capacity used (configured by operator)", f"{capacity_used:.1f}%")
        st.progress(capacity_used / 100)
    else:
        st.info("Filter-volume telemetry and cartridge capacity are needed for a capacity comparison. No remaining-life estimate is generated.")
    st.markdown("**Synthetic RUL model sandbox**")
    st.caption("Runs a chronological model check on generated labels only; this is not filter-performance evidence.")
    if st.button("Run synthetic RUL validation"):
        synthetic_history = generate_synthetic_rul_data(n_samples=150)
        rul_pipeline = XGBoostRULPipeline(walk_forward_cutoff_frac=0.8)
        validation = rul_pipeline.train(synthetic_history)
        prediction_row = synthetic_history.iloc[-1]
        demo_prediction = rul_pipeline.predict_rul(
            dRc_dt_proxy=float(prediction_row["dRc_dt_proxy"]),
            operating_hours=float(prediction_row["operating_hours"]),
            flow_ratio=float(prediction_row["flow_ratio"]),
            pressure_bar=float(prediction_row["pressure_bar"]),
            pressure_rise_rate=float(prediction_row["pressure_rise_rate"]),
        )
        rul_metrics = st.columns(3)
        rul_metrics[0].metric("Synthetic MAE (days)", f"{validation['mae']:.2f}")
        rul_metrics[1].metric("Synthetic RMSE (days)", f"{validation['rmse']:.2f}")
        rul_metrics[2].metric("Synthetic R²", f"{validation['r2']:.3f}")
        st.caption(
            f"Backend: {rul_pipeline.model_backend}; chronological holdout "
            f"{validation['test_set_size']} rows. Demo prediction: {demo_prediction['rul_days']} days."
        )
        st.warning("Synthetic-data metrics do not estimate real cartridge life and must not be reported as field accuracy.")
    latest_alarms = []
    if bool(latest["sensor_fault"]):
        latest_alarms.append("Missing or invalid sensor field")
    if bool(latest["flow_fault"]):
        latest_alarms.append("Invalid feed/permeate/reject flow")
    if bool(latest["pressure_trip"]):
        latest_alarms.append("Pressure exceeds 4.5 bar trip threshold")
    if bool(latest["mass_balance_fault"]):
        latest_alarms.append("RO mass-balance deviation exceeds 5%")
    if latest_alarms:
        st.error("Latest-row alarms: " + "; ".join(latest_alarms))
    else:
        st.success("No latest-row software alarms at configured limits.")
    st.warning("Physical interlocks, pump shutoff, filter-life prediction, and drinking-water safety are not verified by this software.")

with st.expander("Telemetry preview and export"):
    st.dataframe(telemetry, hide_index=True, width="stretch")
    st.download_button(
        "Download prepared telemetry",
        data=telemetry.to_csv(index=False),
        file_name="purifier_telemetry_review.csv",
        mime="text/csv",
    )