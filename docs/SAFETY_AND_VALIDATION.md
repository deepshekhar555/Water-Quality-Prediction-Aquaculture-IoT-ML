# Safety and Validation — AquaSense Pro & ReGen-X (Track 2)

**Source specification:** `BioTwinLabs_Track2.pdf` (AtomQuest 2026 — Track 2)
**Base project:** `L:\aquasensepro\` (Aquaculture water-quality prediction using ML-IoT)
**Critical:** Safety is a priority. Software must not declare water safe for drinking solely from simulated readings or an unvalidated ML prediction.

---

## 1. Safety Principles

1. **Software does not declare water safe.** No ML prediction, simulated reading, or software output alone should ever be used to declare water "safe for drinking." Physical validation is required.

2. **Hardware safety interlocks are independent.** Software monitoring must not replace independent hardware safety interlocks. Solenoid valves, pressure relief, and UV-C isolation must be hardwired, not solely software-driven.

3. **UV-C requires physical validation.** UV-C operation at 265 nm with 99.999% microbial eradication claim requires laboratory validation. Software lamp-hour tracking does not substitute for physical efficacy testing.

4. **Electrical isolation required.** 24V/12V DC via medical-grade optocouplers must isolate water lines from high-voltage AC mains. Double‑reinforced isolation must be verified per safety standards.

5. **Pressure relief is mandatory.** Pressure surges >4.5 bar must trigger auto-isolation of the inlet line via solenoid valves. This must be a physical valve action, not merely a software alert.

6. **Food-contact materials.** All materials contacting water must be NSF-61 compliant (polypropylene housing, silicone seals). This is a hardware requirement; software has no material influence.

7. **Microbial efficacy is unproven in software.** No software claim about microbial reduction should be made without independent laboratory validation.

---

## 2. Hardware Safety Interlocks

| Failure Mode | PDF Specification | Software Response | Hardware Interlock |
|---|---|---|---|
| **Pressure surge** >4.5 bar | Auto-isolate inlet line; shutdown dosing pumps | Publish alert via MQTT; set fail-safe state | Solenoid valve auto-closure (normally-closed, fail-safe) |
| **Electrical fault** (short, overcurrent) | Immediate system shutdown | Cut MQTT publish, set safe state | Optocoupled 24V/12V isolation; external fuse/MCB |
| **Sensor disconnect** (stale timestamp >90 s) | Fail-safe state, alert | Stop readings, disable dosing, alert user | Hardware watchdog; GPIO pull-up/down; separate power domain |
| **UV-C fault** (lamp off, end-of-life) | UV-C auto-off; alert | Disable UV-C in software, publish alert | Physical relay cuts UV-C power; lamp-hour interlock |
| **Electrodialysis over-current** | Shut off dosing pumps | Stop ED cell PWM, publish alert | Current sensor + fuse on ED cell power line |
| **Dosing overdose** (Ca/Mg exceeds setpoint) | Fail-safe shutoff | Close dosing PWM, publish alert | Flow sensor verification + pressure switch; normally-closed dosing valves |

---

## 3. Software Validation Requirements

### 3.1 Sensor Input Validation

- **Out-of-range rejection:** Any parameter value outside physically plausible bounds must be rejected with a quality flag, not silently accepted.
  - pH: valid range 0–14 (hard limits); warning range 2–11 (typical drinking water)
  - TDS: valid range 0–2000 ppm (typical); extreme up to 5000 ppm (alert)
  - Turbidity: valid range 0–1000 NTU; > NTU threshold → alert
  - UV254: valid range 0–3.0 AU (absorbance); > 3 → error state
  - Pressure: valid range 0–10 bar; > 4.5 bar → interlock trigger
  - Flow: valid range 0–10 L/min; negative or zero → disconnect alert

- **Missing-reading detection:** If no new reading within 90 seconds (configurable), mark sensor as `FAULT — DISCONNECTED`. Set fail-safe state. Publish alert.

- **ADC sanity checks:** Voltage saturation (readings at exactly min/max ADC value) → flag as stale/invalid.

### 3.2 Threshold Configuration

- **Configurable thresholds** (not hardcoded) for all alert/fault conditions.
- **Thresholds stored in `.env` or AWS IoT Thing shadow**, not in firmware binary (enables remote reconfiguration without reflashing).
- **Default thresholds** (from PDF):
  - Pressure interlock: 4.5 bar
  - UV254 organic alert: lab-calibrated setpoint
  - Filter replacement: operating volume setpoint per filter type
  - Mineral dosing setpoint: Ca²⁺ and Mg²⁺ max mg/L (configurable)

### 3.3 ML Model Validation

- **Walk-forward / chronological validation only.** No random train/test split. Use `sklearn.model_selection.TimeSeriesSplit` or fixed chronological cutoff.
- **Metrics required (regression):** MAE, RMSE, R². Report all three on held-out test set.
- **Never claim >92% RUL accuracy** unless validated against a clearly defined test dataset using walk-forward validation. Document the dataset, metric, and exact accuracy figure.
- **Baseline vs. ML distinction:** Clearly document that baseline threshold monitoring is separate from XGBoost prognostics. Baseline may produce conservative (safe) estimates; ML may be more precise but requires validation.
- **Model persistence:** Saved model (joblib/pickle) must be versioned. Inference code must verify model version compatibility at startup.
- **Reproducibility:** Set random seeds. Log sklearn version, XGBoost version, Python version, data schema. Do not reuse aquaculture model outputs as purifier predictions.

### 3.4 Simulation Validation

- When running in simulation mode (no hardware), every simulation block must have a **hardware integration checklist** documenting:
  - Real sensor range and accuracy that the simulation must match.
  - Calibration procedure for real hardware.
  - Validation data source (spectrophotometer, flow meter, NIST references).
- Simulation must not be the default production behavior. A build flag or environment variable must enable it.
- All simulation code must be clearly labeled `#ifdef SIMULATION` or equivalent, with a parallel hardware code path.

---

## 4. Empirical / Laboratory Validation Steps

| Feature | Validation Method | Acceptance Criterion |
|---|---|---|
| **TDS→ppm conversion** | Compare ESP32 ADC to reference conductivity meter (e.g., Milwaukee MW-12) | ±10% error across 0–2000 ppm range |
| **pH electrode voltage** | Calibrate with pH 4.01 and 7.01 buffer solutions | Slope within 90–110% of Nernstian (59.16 mV/pH at 25°C) |
| **Turbidity NTU calibration** | Formazin standard series (0, 10, 50, 100 NTU) vs. ADC reading | R² > 0.99 for linear regression; ±5 NTU error at 50 NTU |
| **UV254 → DOC correlation** | Compare UV254 absorbance to spectrophotometer‑measured DOC (NIST-traceable) | slope + intercept from linear regression of known DOC standards; report R² |
| **Flowmeter pulse count** | Known volume (e.g., 1 L) collected timed vs. pulse count | Error < 3% vs. measured volume |
| **Pressure sensor accuracy** | Compare to calibrated gauge (0–10 bar range) | Error < 1% of full scale |
| **ED cell mineral recovery** | Measure Ca/Mg in reject vs. permeate before/after ED (ICP-OES) | Recovery % within design target (±15%) |
| **UV-C microbial efficacy** | Third-party lab test: log reduction of challenge organism (e.g., E. coli) | ≥ 4-log reduction at specified flow rate and dose |
| **Solenoid valve fail-safe** | Pressure step test: surge >4.5 bar → valve closure within 2 s | Valve closed, flow stopped, alert published |

---

## 5. Do NOT Claim (Policy Enforcement)

The following must never be claimed in software, documentation, or public facing material without validated physical evidence:

| Prohibited Claim | Reason |
|---|---|
| "Water is safe for drinking based on sensor readings alone" | Sensors measure physical parameters only; microbial/chemical safety requires laboratory testing. |
| "UV-C makes water 100% sterile" | UV-C efficacy depends on dose, flow, water clarity, and organism type. Physical validation required. |
| ">92% RUL accuracy" | Must be backed by walk-forward validation on a defined test dataset. |
| "Electrodialysis recovers X% minerals" | Depends on reject water chemistry, current, membrane selection, and contact time. |
| "15-second filter replacement" | Mechanical prototype testing required; software cannot validate physical time. |
| "Mineral dosing achieves exact setpoint" | Depends on pump calibration, pressure, viscosity, and line resistance. |
| "XGBoost model is production-ready" | Must pass walk-forward validation with reported MAE, RMSE, R². Not validated → labeled "experimental" or "prototype." |

---

## 6. Validation Method Summary

| Area | Method | When Required |
|---|---|---|
| Sensor accuracy | Bench testing vs. reference instrument | During development; prior to any prototype demo |
| ML model performance | Walk-forward validation; MAE, RMSE, R² | Before any RUL accuracy claim |
| Safety interlocks | Fault injection tests (pressure surge, sensor disconnect) | Before any hardware deployment |
| UV-C efficacy | Third-party laboratory test | Prior to claiming microbial reduction |
| Mass balance (RO) | Verify `Input ≈ Permeate + Reject` across flow scenarios | During system integration |
| Mineral dosing accuracy | Measured vs. setpoint per dosing cycle | During ReGen-X subsystem commissioning |
| Filter bay alignment | Force gauge measurement of push/pull/snap | During Quick-Twist Snap-Lock prototype validation |

---
*End of SAFETY_AND_VALIDATION.md*