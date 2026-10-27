# System Architecture — AquaSense Pro & ReGen-X (Track 2)

**Source specification:** `BioTwinLabs_Track2.pdf` (AtomQuest 2026 — Track 2)
**Base project:** `L:\aquasensepro\` (Aquaculture water-quality prediction using ML-IoT)
**Domain:** Domestic RO purifier with mineral recovery — distinct from aquaculture pond water monitoring.

---

## 1. Overview

The system is a modular, edge-to-cloud architecture that transforms a standard RO purifier into an intelligent water ecosystem. It combines multi-parameter water-quality sensing, automated mineral recovery (ReGen-X), tool-free filter replacement, and data-driven predictive maintenance (RUL).

The four core pillars (from the PDF) are integrated as separate but coordinated modules:

| Pillar | Focus |
|---|---|
| **A** | Multi-parameter water-quality sensing (TDS, pH, Turbidity, UV254) |
| **B** | ReGen-X mineral recovery (electrodialysis, Ca²⁺/Mg²⁺ dosing) |
| **C** | Tool-free filter replacement (Quick-Twist Snap-Lock Filter Bay) |
| **D** | Predictive filter maintenance (RUL with XGBoost) |

---

## 2. High-Level Block Diagram

```
[RAW WATER INLET]
  |
  +--[Optical Turbidity & UV254 Sensors + pH + TDS]--->| Sensor Acquisition (ESP32-S3)
  |                                    |
  v                                    v
[Pre-Filter & Booster Pump]           [Data Validation & Timestamping]
                                    |
                                    v
                                     +--[MQTT over Wi-Fi]---->| AWS IoT Core
                                        (Shadow, Telemetry, OTA)
                                            |
                                            v
                                     +--[Cloud Analytics]----+
                                     |  - XGBoost RUL pipeline |
                                     |  - Mass-balance checks |
                                     |  - Alert generation   |
                                     +-----------------------+

[RO MEMBRANE ASSEMBLY] (Monitored by Pin, Pout Pressure Sensors & Flowmeters)
  |
  +-- Permeate Stream (Pure Water)
  |    |
  |    +--[Post-UV-C Sterilizer]--->[ReGen-X Mineral Dosing]--->[DISPENSER]
  |    |                                       |
  |    |                                           +-->| ReGen-X Electrodialysis Cell
  |    +-- Reject Stream (Brine) ----------------------------| (Recovered Ca²⁺/Mg²⁺)
  |
  +-- Concentrated Waste Discharge (<35% volume)

[CONTROL & CLOUD]: ESP32-S3 Microcontroller ---(MQTT / Wi-Fi)---> AWS IoT Cloud
                                         |
                                         v
                                  Dashboard / Mobile App
                                         |
                                         v
                                  Alerts, Status, History
```

---

## 3. Module Details

### 3.1 Sensor Ingestion & Validation (Edge)
- **Microcontroller:** ESP32-S3
- **Sensors connected:**
  - TDS conductivity electrodes (analog, differential)
  - pH electrode with BNC connector
  - Optical turbidity sensor (NTU, 90° scatter)
  - UV254 module (254 nm UV LED + photodiode, transimpedance amplifier)
  - Pressure transducers (piezoresistive, 0-10 bar inlet/permeate/reject)
  - Hall-effect flowmeters (Fin = inlet, Fout = permeate)
  - UV-C lamp hour counter
- **Per-reading data format:** `{timestamp, sensor_id, parameter, value, quality, unit}`
- **Validation:** out-of-range check, sanity bounds, missing-reading timeout, ADC saturation flag
- **Output:** Validated sensor payload published via MQTT

### 3.2 RO Process & Water-Flow Simulation (Edge/Edge-Coordinator)
- **Pressure sensors:** `Pin` (inlet), `Pmembrane` (trans-membrane), `Pout` (permeate)
- **Flowmeters:** `Fin` (inlet), `Fout` (permeate)
- **Mass-balance enforcement:** `Input_volume ≈ Permeate_volume + Reject_volume`
- **Recovery ratio:** `Recovery = Permeate / Input` (target < 35% reject, i.e. > 65% recovery adjustable)
- **Flux calculation:** `J = dP / (u * (Rm + Rc))` — tracked via dRc/dt (cake/foulant resistance change rate)
- **Simulation mode:** When physical hardware is unavailable, a software simulator computes permeate/reject split using configurable recovery ratio and validates mass balance.

### 3.3 ReGen-X Mineral Recovery Module (Edge)
- **Electrodialysis (ED) cell:** 12V DC, <15W, selective cation/anion exchange membranes
- **Control:** PWM-driven micro-peristaltic dosing pumps
- **Ions recovered:** Ca²⁺ and Mg²⁺ from reject stream
- **Re-injection:** Controlled dose into post-RO permeate stream
- **Tracking variables:**
  - `rejected_vol` (L) — total reject volume
  - `permeate_vol` (L) — total pure water volume
  - `ca_recovered_mg` — calcium recovered (mg)
  - `mg_recovered_mg` — magnesium recovered (mg)
  - `dosing_setpoint_ca_mgL` — max calcium dosage setpoint (configurable)
  - `dosing_setpoint_mg_mgL` — max magnesium dosage setpoint (configurable)
- **Fail-safe shutoff:** Dosing stops on over-limit, pressure fault, or sensor disconnect.
- **Simulation mode:** When physical ED cell is unavailable, a software model computes mineral recovery from reject flow rate, current, and time. Output is clearly labeled as simulated.

### 3.4 Quick-Twist Snap-Lock Filter Bay (Edge)
- **Mechanical design:** 3D-printed enclosure with snap-lock closure mechanism. Sealing requirements: O-ring or gasket, food-grade silicone, NSF-61 compliant materials.
- **Software tracking:** 
  - `filter_id` (UUID, etched or printed on bay)
  - `install_date` (ISO-8601)
  - `operating_volume_liters` (counter, incremented by Fin/Flowmeter data)
  - `replacement_status` enum: `NEW`, `GOOD`, `EXPIRED`
  - `maintenance_history` (array of `{date, action, volume, filter_id}`)
- **Alignment/check logic:** State machine: `IDLE → REMOVAL → ALIGNMENT → LOCK → IDLE`. Alignment detected via proximity sensor or software state confirmation.
- **Replacement workflow:** User removes old filter, inserts new bay snaps into place. System verifies alignment lock status before resuming operation.
- **Do not claim:** 15-second physical replacement without prototype testing. Software can simulate the workflow.

### 3.5 Predictive Maintenance & RUL (Edge + Cloud)
- **Features collected:** dRc/dt (membrane resistance change), operating hours, Fin/Fout flow differential, Pin/Pmembrane pressure differential
- **Baseline monitoring:** Fixed thresholds on dRc/dt, flow ratio, pressure differential
- **ML pipeline:** XGBoost model for dynamic RUL prediction
  - Input features: `[dRc_dt, operating_hours, flow_diff, pressure_diff]`
  - Target: `RUL_days`, `RUL_liters`
  - Training: walk-forward / chronological validation
  - Evaluation: MAE, RMSE, R²
  - Persistence: model saved via joblib, loaded at startup
- **Do not claim:** >92% RUL accuracy without validated test dataset and walk-forward metric.
- **Dual model capability:** Baseline threshold alerts + XGBoost prognostics. Distinction clearly documented between baseline and ML model performance.

### 3.6 UV-C Sterilization Monitoring (Edge)
- **UV-C lamp:** 265 nm, 99.999% microbial eradication rating
- **Monitoring:** Lamp hours counter, intensity decay tracking, status flag
- **Safety interlocks:** UV-C auto-off on pressure surge (>4.5 bar), electrical fault, sensor disconnect, or maintenance interval exceeded
- **Do not claim:** Microbial efficacy without physical validation. Software monitoring does not replace independent hardware safety interlocks.

### 3.7 Safety & Fault Handling (Edge)
- **Pressure relief:** Solenoid shut-off valves auto-isolate inlet line on pressure surge >4.5 bar
- **Electrical isolation:** 24V/12V DC via medical-grade optocouplers isolates water lines from high-voltage AC mains
- **Sensor disconnect:** Stale timestamp threshold (e.g., no reading >90s) → fail-safe state, alert
- **Fail-safe defaults:** Dosing pumps off, UV-C off, inlet valve closed on any critical fault
- **Materials:** Food-grade NSF-61 compliant (polypropylene housing, silicone seals)

### 3.8 Dashboard & API Integration
- **Backend:** AWS IoT Core shadow + CloudWatch metrics
- **API endpoints (existing application, if present):**
  - `GET /sensor-readings` — latest validated sensor data
  - `GET /filter-status` — filter identity, operating volume, replacement status
  - `GET /rul-prediction` — remaining useful life (days, liters)
  - `GET /system-status` — overall system health, active alerts
  - `POST /mineral-dose` — configure Ca/Mg dosing setpoints
- **Historical readings:** Time-series dashboard showing TDS, pH, Turbidity, UV254, recovery metrics, RUL trend
- **Alerts:** Abnormal readings, fault triggers, dosing over-limit, filter expiration, maintenance due

### 3.9 Cloud Deployment (AWS IoT Core)
- **Thing registration:** One AWS IoT Thing per device (ESP32-S3)
- **Certificates:** X.509 certificates for MQTT TLS authentication (no hardcoded keys)
- **Shadow document:** Desired/ reported state for dosing setpoints, filter status, RUL
- **OTA updates:** AWS IoT Jobs for firmware over-the-air updates
- **Environment config:** `.env.example` with placeholders only (no real credentials in source)

---

## 4. Data Flow

1. **Sensor acquisition** (ESP32-S3) → **validation** → **MQTT publish** (topic: `aqua/sensors/{device_id}`)
2. **MQTT broker** (AWS IoT Core or local Mosquitto) → **cloud analytics** (XGBoost RUL pipeline)
3. **Cloud** → **MQTT subscribe** → **dashboard** (historical trends, filter status, RUL)
4. **User action** (e.g., filter replacement) → **local state update** → **MQTT publish** → **cloud sync**
5. **Fault detection** → **fail-safe action** (solenoid close, dosing off, UV-C off) + **alert publish**

---

## 5. Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| **Edge** | ESP32-S3 | MicroPython or Arduino-ESP32 core |
| **Sensing** | Analog electrodes, optical sensors (Turbidity, UV254), pressure transducers, Hall-effect flowmeters | Calibration per sensor type |
| **Connectivity** | MQTT over Wi-Fi | AWS IoT Core or local broker (Mosquitto) |
| **Cloud** | AWS IoT Core | Shadow, Jobs, Certificates. .env.example for placeholders. |
| **ML** | XGBoost | Training in Python; inference on edge or cloud. Walk-forward validation. |
| **Visualization** | Grafana / custom dashboard | Time-series, filter health, recovery metrics |
| **Persistence** | JSON logs + optionally SQLite on edge | Sensor history, maintenance records |
| **Firmware** | ESP32 Arduino core + FreeRTOS tasks | Modular tasks: sensor, MQTT, fault monitoring, dosing control |

---

## 6. Simulation vs. Hardware

| Feature | Simulation (development) | Physical hardware (validation) |
|---|---|---|
| RO permeate/reject flow | Configurable recovery ratio; mass-balance verified | Flowmeters, booster pump, actual membrane |
| Electrodialysis mineral recovery | Software model: current × time → Ca/Mg dose | Custom ED cell with ion-exchange membranes |
| UV254 → DOC/TOC | Fixed calibrated curve (NIST-traceable reference) | Spectrophotometer reference measurement |
| XGBoost RUL model | Trained on synthetic data with known ground truth | Collected from clogging test rig with real filter degradation |
| Filter bay alignment | Software state machine with mock sensor | 3D-printed prototype + proximity sensor + force gauge |
| UV-C sterilization | Lamp-hour counter, intensity decay model | Physical UV-C module with microbe test |

All simulation code is clearly labeled and separated from hardware-dependent code paths.

---
*End of SYSTEM_ARCHITECTURE.md*