# Feature Gap Analysis — AquaSense Pro & ReGen-X (Track 2)

**Specification source:** `BioTwinLabs_Track2.pdf` (AtomQuest 2026 — Track 2: Water Purifier)
**Existing project:** `L:\aquasensepro\` (Aquaculture water-quality prediction using ML-IoT)
**Comparison basis:** PDF is the authoritative functional specification. Existing project concerns aquaculture pond water; PDF concerns a domestic RO purifier. Domain change is noted per Phase Three.

---

## Legend

| Column | Description |
|---|---|
| **PDF requirement** | What the PDF specifies as a functional requirement |
| **Existing implementation** | File and code that currently implements (or attempts) this feature |
| **Status** | `implemented` — fully functional in existing code; `partial` — partially present, needs extension; `missing` — not present; `not applicable` — does not apply to current domain |
| **Reusable components** | Code/modules from the existing project that can be reused (with domain adaptation noted) |
| **Required changes or new modules** | What needs to be added, modified, or built from scratch |
| **Validation method** | How the feature can be validated (unit test, simulation, hardware, etc.) |
| **Hardware dependency / simulation** | Whether the feature requires physical hardware or can run in simulation |

---

## A. Multi-parameter Water-Quality Sensing

| # | PDF requirement | Existing implementation | Status | Reusable components | Required changes / new modules | Validation method | HW / sim |
|---|---|---|---|---|---|---|---|
| A1 | **TDS/conductivity** measurement — dual TDS electrodes at inlet and post-RO, conductivity monitoring | No TDS/conductivity sensor or code. Existing aquaculture notebook predicts DO using pH, temperature, and turbidity only; no conductivity or TDS. | `missing` | None | Add TDS conductivity measurement subsystem (analog electrodes or dedicated TDS sensor). Implement ESP32 acquisition of raw ADC values, conversion to TDS (ppm) using calibration factor. | Unit test: verify ADC-to-TDS conversion with known standards. Integration: verify readings within ±10% of reference meter. | ESP32 edge; simulation: fixed calibration curves for development. |
| A2 | **pH** measurement — pH sensor with calibration status, timestamps, health checks | Arduino firmware reads pH via analog voltage with fixed calibration (`calibration_value = 21.34 - 0.7`). Notebook computes DO from pH but no calibration status or timestamps. | `partial` | pH reading code in Arduino (`sketch_aquaculture_copy_20240920175008.ino`) and pH→DO formula in notebook. | Extend pH acquisition with: calibration status tracking, timestamp attachment, voltage validation, missing-reading detection. Distinguish measured pH from ML-estimated values. | ESP32; unit test: verify pH voltage mapping against known buffers. | ESP32 edge; simulation: fixed calibration curve for dev. |
| A3 | **Optical turbidity** in NTU — inline Nephelometric turbidity sensor | Arduino maps raw ADC to 0-100 turbidity units (line `turbidity = map(turbidityRawValue, 0, 1023, 0, 100)`). Notebook uses turbidity as DO input feature. | `partial` | Turbidity reading in Arduino and notebook feature column. | Extend turbidity: (a) use proper NTU calibration (not arbitrary 0-100 map), (b) add sensor health checks, (c) add missing-reading detection, (d) distinguish measured NTU from ML-estimated values. | ESP32; unit test: verify ADC-to-NTU conversion with calibration fluids. | ESP32 edge; simulation: fixed lookup table for development. |
| A4 | **UV254** optical absorption as organic-contamination proxy — 254 nm UV LED + photodiode pair measuring UV Absorbance correlating with DOC/TOC | No UV254 sensor, no UV LED, no photodiode, no optical absorption measurement. Entirely absent. | `missing` | None | Build UV254 acquisition subsystem: 254 nm UV LED + photodiode pair, transimpedance amplifier, ESP32 ADC reading. Implement UV Absorbance → DOC/TOC correlation (lab-calibrated). Clearly document that UV254 is a proxy, not a direct measurement of every organic contaminant. | Integration: verify UV254 response vs. spectrophotometer reference. Unit test: verify ADC response to known NDUV solutions. | ESP32 edge; simulation: fixed UV254→DOC curve for development without hardware. |
| A5 | **ESP32-based sensor acquisition and data validation** | Arduino firmware on unspecified microcontroller; no ESP32, no MQTT, no cloud streaming. Notebook runs in Colab/Jupyter, not on device. | `missing` | Algorithmic ideas (sensor reading, averaging) can be adapted. | Rewrite sensor acquisition for ESP32-S3 platform. Implement data validation: out-of-range detection, sanity checks, timestamping, missing-reading flags. | Unit test: verify ESP32 sensor pipeline end-to-end with mock sensor data. | ESP32-S3 (required); simulation: mock sensor data pipeline for development. |
| A6 | **Calibration status, timestamps, sensor health, missing-reading detection** | No calibration status tracking, no standardized timestamps, no sensor health flags. Arduino prints raw values; notebook reads Excel with no metadata. | `missing` | None | Add calibration version/date per sensor type; attach ISO-8601 timestamp to every reading; implement sensor health enum (OK/WARNING/FAIL); add missing-reading detection (timeout, out-of-range, ADC saturation). | Unit test: verify health flags trigger correctly on simulated sensor failures. | ESP32 edge; simulation: mock health flags for development. |

---

## B. ReGen-X Mineral Recovery

| # | PDF requirement | Existing implementation | Status | Reusable components | Required changes / new modules | Validation method | HW / sim |
|---|---|---|---|---|---|---|---|
| B1 | **Model RO permeate and reject-water streams** — track input water, permeate, reject volume | No RO modeling, no permeate/reject tracking. Existing project is aquaculture pond water, no RO membrane. | `missing` | None | Build RO process simulation module: model feed water splitting into permeate (pure) and reject (brine) streams. Track volumetric flow rates at each branch using Hall-effect flowmeters (Fin, Fout). Implement mass balance: `Input = Permeate + Reject`. | Unit test: verify mass balance holds for simulated flow scenarios. Integration: verify with physical flow sensors when available. | Simulation-first; hardware integration when electrodialysis cell is available. |
| B2 | **Separate mineral-recovery module for calcium and magnesium** — electrodialysis to extract Ca2+/Mg2+ from reject stream | No mineral recovery, no Ca2+/Mg2+ tracking. | `missing` | None | Design electrodialysis (ED) cell control module: cation/anion exchange membranes, 12V DC <15W drive. Implement PWM micro-dosing pumps for controlled Ca2+/Mg2+ re-injection into permeate. Track recovered mineral quantities (mg/L). | Unit test: verify ED cell current/voltage characteristics. Integration: verify mineral dosage vs. target setpoints. | Simulation of ED process (concentration polarization, membrane selectivity). HW: custom ED cell required for physical validation. |
| B3 | **Electrodialysis process and controlled mineral dosing** | Not applicable. | `not applicable` | None | See B2. Add dosing pump control with PWM, flow verification, and overdose prevention. | Unit test: verify pump delivery rate vs. setpoint. | Simulation: peristaltic pump speed → flow rate conversion. HW: actual peristaltic pump. |
| B4 | **Track input water, permeate, reject volume, recovered mineral quantities, mass balance** | Not applicable. | `not applicable` | None | Implement data structure: `WaterMassBalance(input_vol, permeate_vol, reject_vol, ca_recovered_mg, mg_recovered_mg)`. Enforce `input ≈ permeate + reject` and mineral mass balance. | Unit test: verify balance error < 2% for simulated scenarios. | Simulation-only for initial development. |
| B5 | **Configurable dosing limits, sensor checks, fail-safe shutoff** | Not applicable. | `not applicable` | None | Configurable max Ca/Mg dosing setpoints (mg/L). Sensor checks: verify flow during dosing, verify pressure limits. Fail-safe: shut off dosing pumps on over-limit, disconnect, or pressure fault. | Unit test: verify shutoff triggers on oversetpoint and sensor fault. | Simulation for dosing logic; HW: actual solenoid/peristaltic valves with safety interlocks. |

---

## C. Tool-Free Filter Replacement

| # | PDF requirement | Existing implementation | Status | Reusable components | Required changes / new modules | Validation method | HW / sim |
|---|---|---|---|---|---|---|---|
| C1 | **Quick-Twist Snap-Lock Filter Bay software interface and documentation** | No filter bay, no software interface. Arduino LCD displays turbidity/volume but no filter tracking. | `missing` | None | Design software interface for filter bay: filter identity tracking, installation date, operating volume counter, replacement status, maintenance history log. Implement alignment/snap-lock status checks (electronic sensor or software state machine). | Unit test: verify state transitions (install → operate → replace). Integration: verify alignment check on filter installation. | Simulation: software state machine without physical prototype. HW: 3D-printed snap-lock enclosure + proximity sensor for validation. |
| C2 | **Track filter identity, installation date, operating volume, replacement status, maintenance history** | Not present. | `missing` | None | Add filter entity: `filter_id`, `install_date`, `operating_volume_liters`, `replacement_status` (NEW/GOOD/EXPIRED), `maintenance_history` (array of {date, action, volume}). | Unit test: verify volume counter and status logic for sequential filter lifetimes. | Simulation: fixed filter lifetimes for development. HW: physical filter bay for endurance testing. |
| C3 | **Simulated replacement workflow and alignment/lock-status checks** | Not present. | `missing` | None | Implement replacement workflow state machine: `IDLE → REMOVAL → ALIGNMENT → LOCK → IDLE`. Include alignment check (snap-lock detected, push/pull force gauge). Document mechanical design, sealing requirements, hardware validation steps. | Unit test: verify state machine transitions succeed with valid input and fail on misalignment. | Simulation: state machine with mock sensor inputs. HW: physical snap-lock mechanism with force sensor. |
| C4 | **Document mechanical design, sealing requirements, hardware validation** | Not present. | `not applicable` (documentation only) | None | Create CAD documentation and sealing specs for Quick-Twist Snap-Lock Filter Bay. Note: do not claim functional 15-second physical replacement without prototype testing. | N/A — documentation of mechanical design. | N/A. |

---

## D. Predictive Filter Maintenance (RUL Prediction)

| # | PDF requirement | Existing implementation | Status | Reusable components | Required changes / new modules | Validation method | HW / sim |
|---|---|---|---|---|---|---|---|
| D1 | **Collect inlet/outlet flow, pressure, operating time, and other available sensor features** | Arduino collects temperature, pH, turbidity. No flow or pressure sensors. No operating time tracking beyond millis() in loop. | `missing` | None | Add Hall-effect pulse flowmeters (Fin, Fout) and piezoresistive pressure transducers (Pin, Pmembrane). Track operating hours/days. Implement data logging with timestamps. | Unit test: verify flow and pressure readings vs. reference. | ESP32 edge; simulation: fixed flow/pressure profiles for development. |
| D2 | **Estimate filter degradation and Remaining Useful Life (RUL) in days and liters** | Notebook predicts DO and WaterQuality using Linear Regression; no RUL, no filter degradation model. | `missing` | None | Build RUL prognostics pipeline: (a) feature engineering from flow/pressure/operating-time data, (b) baseline threshold-based monitoring (Darcy's Law: J = dP / (u * (Rm + Rc))), (c) XGBoost model for dynamic RUL in days and liters. | Chronological / walk-forward validation for time-series. Evaluate MAE, RMSE, R². Never claim >92% RUL accuracy without validated test dataset. | XGBoost model training on synthetic or collected data. |
| D3 | **Baseline threshold-based monitoring and ML-based prognostics pipeline** | Linear Regression model in notebook (not XGBoost, not for RUL). MSE evaluation only. | `partial` | Linear Regression notebook code (can be adapted as baseline). | Implement baseline: fixed thresholds on dRc/dt (membrane resistance change rate). Add XGBoost pipeline: training, inference, evaluation, persistence (save/load model). | Walk-forward validation on time-series data. Report MAE, RMSE, R². | Python environment with xgboost. Data: simulated or collected from prototype. |
| D4 | **Use XGBoost where supported by the available data** | Not used. | `new` | None | Integrate XGBoost for RUL prediction. Train on features: dRc/dt, operating hours, flow differential, pressure differential. Validate with walk-forward split (not random split). | Walk-forward validation. Report MAE, RMSE, R² on held-out chronological test set. | Python + xgboost library. |
| D5 | **Training, inference, model evaluation, data validation, model persistence** | Notebook trains LinearRegression and computes MSE on random train/test split — inappropriate for time-series. | `partial` | Notebook structure (data loading, train/test split, evaluation metrics) can be refactored. | Refactor training pipeline: use walk-forward validation instead of random split. Add model persistence (joblib/pickle). Add inference routine. Add data validation (missing values, outliers). | Walk-forward validation. MAE, RMSE, R². Model saved/loaded for production use. | Python environment. |
| D6 | **Chronological or walk-forward validation for time-series data, preventing data leakage** | Notebook uses random `train_test_split` (random state=42) — leaks future data into training. | `partial` | Code structure can be adapted. | Replace random split with walk-forward/chronological validation. First N% of data for training, remaining for testing. No future data in training. | Verify that walk-forward CV produces different (typically worse) metrics than random split. | Python + sklearn TimeSeriesSplit. |
| D7 | **Evaluate MAE, RMSE, and R² for regression, as appropriate** | Only MSE reported in notebook. | `partial` | Notebook evaluation code. | Add MAE and RMSE computation alongside MSE. Report all three for each evaluation run. | Compute on walk-forward test set. | Python + sklearn. |
| D8 | **Never claim >92% RUL accuracy unless validated against a clearly defined test dataset and metric** | Not applicable (no RUL claims). | `not applicable` | None | Policy: all RUL accuracy claims must be backed by evaluation on a clearly defined test dataset using walk-forward validation. Document dataset, metric, and accuracy. | N/A — policy enforcement. | N/A. |

---

## E. Infrastructure and Integration

| # | PDF requirement | Existing implementation | Status | Reusable components | Required changes / new modules | Validation method | HW / sim |
|---|---|---|---|---|---|---|---|
| E1 | **ESP32-S3 for edge acquisition and control** | Arduino on unknown chip; no ESP32, no edge control. | `missing` | Algorithmic ideas can be adapted. | Port all sensor acquisition, data validation, and MQTT streaming to ESP32-S3 platform. Implement Arduino-FreeRTOS-like task structure. | Unit test: ESP32 build and mock sensor pipeline. | ESP32-S3 (required for production). |
| E2 | **MQTT over Wi-Fi for telemetry** | No MQTT, no Wi-Fi, no telemetry. Notebook outputs to Colab stdout. | `missing` | None | Implement MQTT client on ESP32-S3 connecting to AWS IoT Core (or local broker). Topics: sensor readings, filter status, RUL predictions, system alerts. | Unit test: MQTT connect/publish with mock broker. Integration: verify AWS IoT Core receipt. | Wi-Fi network; simulation: local Mosquitto broker for development. |
| E3 | **AWS IoT Core for cloud connectivity** | Not present. | `missing` | None | Configure ESP32 to authenticate with AWS IoT Core (certificates). Create shadow topics, thing registration. Implement over-the-air (OTA) update capability. | Integration: verify device thing creation and shadow updates. | AWS account (no real credentials in source — use .env.example). | Simulation: local AWS IoT Core endpoint mock for development. |
| E4 | **XGBoost for filter prognostics** | Linear Regression only; no XGBoost. | `new` | None | Integrate XGBoost model (as identified in D4) for deployment on edge or cloud. Optimize for ESP32-S3 if needed (quantization, limited features). | Verify XGBoost model inference produces RUL estimates within expected range. | Python training; C/MicroXGBoost for edge inference if needed. | |
| E5 | **UV-C sterilization monitoring and hardware safety interlocks** | No UV-C, no sterilization, no safety interlocks. | `missing` | None | Implement UV-C lamp monitoring (hours, status). Hardware interlocks: UV-C auto-off on fault, pressure surge, or sensor disconnect. Monitor UV-C dosage (mJ/cm²). | Unit test: verify interlock triggers on simulated faults. | UV-C LED module; simulation: lamp-hour counter for development. | |
| E6 | **Pressure, flow, and sensor-disconnect fault handling** | No pressure sensors; no flow monitoring beyond rudimentary turbidity; no disconnect handling (Arduino has commented-out check). | `missing` | None | Implement fault detection: pressure >4.5 bar → auto-isolate inlet via solenoid valve. Flow disconnect: Fin/Fout mismatch → alert. Sensor disconnect: timeout, stale timestamp → fail-safe state. | Unit test: verify fault handling triggers correctly. | ESP32 + pressure/flow sensors; simulation: fault profiles for development. | |

---

## F. Cross-Cutting: Domain Adaptation Notes

The existing aquaculture project and the PDF target a domestic RO purifier. These are different domains. The following notes apply:

- **Do not reuse aquaculture labels** (pond, dissolved oxygen, fish health) as purifier predictions.
- **Do not reuse aquaculture datasets** (pond water samples, DO measurements) as RO permeate/reject data.
- **Do not reuse existing model outputs** (DO predictions, WaterQuality scores) as purifier predictions.
- **Reusable architectural patterns**: sensor data ingestion, timestamping, MQTT telemetry, baseline ML pipeline structure, unit conversion, input validation.
- **Reusable code (with domain adaptation)**: unit conversion functions, threshold configuration, input validation, data preprocessing pipelines (adapted for new parameter set).
- **Not reusable**: dissolved oxygen formula (specific to aquaculture), pond temperature/turbidity ranges, aquaculture ML model outputs.

---

## G. Summary of Status Counts

| Status | Count |
|---|---|
| implemented | 0 |
| partial | 5 (pH, turbidity, Linear Regression baseline, walk-forward/Va validation structure, MSE evaluation) |
| missing | 28 |
| not applicable | 4 (RO modeling, ED mineral dosing, mechanical design docs, >92% RUL policy) |

**Total PDF requirements evaluated: 37**

---
*End of FEATURE_GAP_ANALYSIS.md*