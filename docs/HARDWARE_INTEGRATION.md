# Hardware Integration — AquaSense Pro & ReGen-X (Track 2)

**Source specification:** `BioTwinLabs_Track2.pdf` (AtomQuest 2026 — Track 2)
**Base project:** `L:\aquasensepro\` (Aquaculture water-quality prediction using ML-IoT)
**Important:** This document maps PDF-specified hardware to the existing aquaculture platform and defines new hardware requirements for the purifier system.

---

## 1. Edge Microcontroller: ESP32-S3

| PDF Specification | Existing Project Equivalent | Action Required |
|---|---|---|
| ESP32-S3 for edge acquisition and control | Arduino Nano 33 IoT (implicit) or standalone ATMega328p on Arduino firmware (`sketch_aquaculture_copy_20240920175008.ino`) | Port all sensor acquisition, validation, and MQTT streaming to ESP32-S3. The existing Arduino code is a starting point for logic but must be rewritten for ESP32-S3 platform (Wi-Fi, MQTT, more pins, dual-core). |

### 1.1 Pin Mapping (Existing → New)

| Function | Existing Arduino Pin | ESP32-S3 Pin | Notes |
|---|---|---|---|
| pH sensor analog | A3 (analogRead) | GPIO36 (ADC1_CH0) | ESP32 has 3x more ADC channels; pH circuit unchanged |
| Turbidity sensor analog | A1 | GPIO39 (ADC1_CH1) | Same analog principle, different silicon |
| DS18B20 temperature | A0 (OneWire) | GPIO4 (D2) / GPIO16 (D0) | OneWire still valid on ESP32 |
| LCD I2C | A4 (SDA), A5 (SCL) | GPIO8 (SDA1), GPIO9 (SCL1) | I2C bus remains; LCD code adapts |
| Serial debug | USB Serial | UART2 (GPIO16/D0, GPIO17/D1) | Keep for debug; redirect to Wi-Fi/MQTT for telemetry |

### 1.2 New ESP32-S3 Additions

- Wi-Fi subsystem (802.11 b/g/n) for MQTT connectivity
- Additional ADC channels for TDS second electrode
- Additional UART for GPS or secondary sensor bus
- More PWM channels for dosing pump control
- Built-in USB-JTAG for debugging

---

## 2. Multi-Parameter Sensors

| PDF Parameter | Sensor Type | Existing Project Equivalent | Integration Action |
|---|---|---|---|
| **TDS/conductivity** | Dual conductivity electrodes (inlet + post-RO) | Not present in aquaculture project | Add TDS conductivity sensor module (e.g., DFRobot SE-12 or custom electrode + amplifier). Connect to ESP32 ADC second channel. Calibration: known TDS standards (0, 500, 1413, 12880 ppm). |
| **pH** | pH electrode with BNC connector, amplifier | Arduino reads pH via analog voltage (`ph_act = -5.70 * volt + calibration_value`) | Keep pH circuit; update ESP32 code with calibration status tracking, timestamps, missing-reading detection. |
| **Optical turbidity (NTU)** | 90° scatter sensor, LED + photodiode | Arduino maps raw ADC to 0-100 (arbitrary). Notebook uses as DO input. | Replace arbitrary 0-100 map with proper NTU calibration using Formazin standards (0, 10, 50, 100 NTU). Add sensor health checks (ADC saturation, ambient light rejection). |
| **UV254** | 254 nm UV LED + photodiode, transimpedance amplifier | Absent | New hardware module: UV LED at 254 nm, photodiode (e.g., SFH 27), TIA (e.g., OPA333). ESP32 ADC reads photodiode current. Calibration: correlate UV254 absorbance with NIST-traceable DOC standards. Document: UV254 is a proxy for organic contamination, not a direct measurement of every contaminant. |
| **Pressure** | Piezoresistive transducers, 0-10 bar | Not present | Add pressure breakout board (e.g., MPX4250DP for 0-250 kPa range, or 0-10 bar industrial sensor). Connect to ESP32 ADC or dedicated SPI pressure sensor. Three sensors: `Pin` (inlet), `Pmembrane` (TM), `Pout` (permeate). |
| **Flow** | Hall-effect pulse flowmeters (Fin, Fout) | Not present (turbidity-based flow reference only) | Add two Hall-effect flow sensors (food-grade, 0.5-5 L/min). ESP32 counts pulses per second. `Fin` = inlet, `Fout` = permeate. Flow differential → filter clogging indicator. |
| **UV-C monitoring** | 265 nm LED, hour counter, intensity decay | Not present | Add UV-C lamp with hour-counter PCB. ESP32 tracks operating hours. Interlock: auto-off after service interval or on fault. |

---

## 3. ESP32-S3 Wiring Summary

```
Sensors power domain: 5V or 3.3V (sensor-dependent), regulated by ESP32 3.3V rail or external regulator.

ADC inputs (3.3V tolerant, use voltage dividers for 5V sensors):
  - GPIO36 (ADC1_CH0)  ← pH electrode (with amplifier)
  - GPIO39 (ADC1_CH1)  ← Turbidity sensor
  - GPIO34 (ADC1_CH6)  ← TDS electrode 2 (post-RO)
  - GPIO35 (ADC1_CH7)  ← TDS electrode 1 (inlet)

Pressure sensors (may use dedicated ADC or SPI):
  - GPIO32 (GPIO1)     ← Pin (inlet pressure)
  - GPIO33 (GPIO2)     ← Pmembrane (TM pressure)
  - GPIO25 (GPIO6)     ← Pout (permeate pressure)

Flowmeters (Hall-effect, pulse input):
  - GPIO18 (GPIO8)     ← Fin (inlet pulse count)
  - GPIO19 (GPIO9)     ← Fout (permeate pulse count)

UV254 module:
  - GPIO26 (GPIO3)     ← Photodiode TIA output (ADC or external interrupt)

UV-C lamp hour counter:
  - GPIO27 (GPIO4)     ← UV-C status/interrupt

MQTT connectivity:
  - GPIO21 (GPIO11)    ← SDA (I2C for sensors)
  - GPIO22 (GPIO12)    ← SCL (I2C for sensors)

Note: GPIO pins are interchangeable per ESP32-S3 schematic; the above is a representative mapping.
```

---

## 4. Communication: MQTT over Wi-Fi

| PDF Specification | Existing Project | Action |
|---|---|---|
| MQTT over Wi-Fi for telemetry | Not present (notebook runs in Colab, outputs to stdout) | Implement MQTT client on ESP32-S3. Connect to local Mosquitto broker or AWS IoT Core. Topics: `aqua/sensors/{device_id}`, `aqua/filter/{device_id}`, `aqua/rul/{device_id}`, `aqua/status/{device_id}`. |

### 4.1 MQTT Topic Design

| Topic | Payload | Direction |
|---|---|---|
| `aqua/sensors/{device_id}` | `{timestamp, pH, temp, turbidity_ntu, uv254_abs, tds_ppm, pressure_in_bar, pressure_tm_bar, pressure_out_bar, flow_fin_lpm, flow_fout_lpm, filter_operating_vol_l, uv_c_hours}` | Device → Cloud |
| `aqua/filter/{device_id}` | `{status, install_date, operating_vol_l, maintenance_history[]}` | Device → Cloud |
| `aqua/rul/{device_id}` | `{rul_days, rul_liters, model_version, confidence}` | Device → Cloud (periodic) |
| `aqua/status/{device_id}` | `{health, active_alerts[], fault_codes[]}` | Device → Cloud |
| `aqua/mineral-dose/{device_id}` | `{ca_setpoint_mgL, mg_setpoint_mgL}` | Cloud → Device (desired) |
| `aqua/shadow/{device_id}` | Desired/reported state | AWS IoT Core |

### 4.2 Wi-Fi Credentials

- **Never hardcode** Wi-Fi SSID or password in source.
- Provide `.env.example` with placeholders:
  ```
  WIFI_SSID=YOUR_WIFI_SSID
  WIFI_PASSWORD=YOUR_WIFI_PASSWORD
  AWS_IOT_ENDPOINT=YOUR_AWS_IOT_ENDPOINT
  AWS_ROOT_CA=path/to/root/ca.pem
  AWS_CERTIFICATE=path/to/device/cert.pem
  AWS_PRIVATE_KEY=path/to/private/key.pem
  ```
- Use environment variables loaded at runtime (not committed to VCS).

---

## 5. Cloud: AWS IoT Core

| PDF Specification | Existing Project | Action |
|---|---|---|
| AWS IoT Core for cloud connectivity | Not present | Set up AWS IoT Thing per device. Use X.509 certificates for TLS authentication. Create shadow topics. Implement OTA Jobs for firmware updates. |

### 5.1 AWS IoT Core Resources

- **One Thing per ESP32-S3 device**
- **Three certificates** per thing (Root CA, Device Certificate, Private Key). Never commit to repo.
- **Shadow document** per thing (JSON, desired + reported state)
- **MQTT over WSS** (port 443) to `{endpoint}.iot.{region}.amazonaws.com`
- **Topic prefix:** `aqua/{thing_name}/`

### 5.2 Cloud Analytics Pipeline (Optional)

- **MQTT → AWS Lambda** → XGBoost inference → RUL update → DynamoDB → Grafana dashboard
- **Or** local Mosquitto + Python subscriber on development laptop, with cloud sync when ready.

---

## 6. Bill of Materials (BOM) Cross-Reference

| Subsystem | PDF Est. Cost (INR) | Existing Project Equivalent | New Component Needed | Notes |
|---|---|---|---|---|
| ESP32-S3 IoT Microcontroller | INR 650 | Not present (Arduino unknown chip) | ESP32-S3 Dev Kit | Standard local stock; required for all new functionality |
| Multi-spectral Optical (UV254 + Turbidity pair) | INR 1,800 | Turbidity only (Arduino A1) | UV254 module + 3D-printed housing | Custom optical chamber; use standard UV/photodiode pair |
| Pressure Sensors (0-10 bar piezoresistive) | INR 900 | Not present | 3x pressure transducers | Industrial stock; 1/4 in NPT threaded |
| Hall Effect Flowmeters | INR 500 | Not present | 2x flow sensors | Local stock; food-grade |
| Electrodialysis Recovery Cell + Ion Membranes | INR 2,400 | Not present | Custom ED stack + cation/anion membranes | High sourcing risk; pre-order membranes early |
| PWM Micro-Dosing Peristaltic Pump | INR 750 | Not present | 2x peristaltic pumps (Ca, Mg) | Standard stock; 12V DC |
| Quick-Twist Snap-Lock Filter Bay | INR 1,200 | LCD display only | 3D-printed enclosure + snap-lock mechanism | In-house FDM/SLA printing with PETG/ABS |
| RO Booster Pump, Valves, UV-C LED & Tubing | INR 2,300 | Not present | RO booster pump, solenoid valves, UV-C module | Standard Atomberg/OEM RO replacement parts |
| **Total Prototype Cost** | **INR 10,500** | — | **~INR 9,650 additional** | Target commercial BOM at scale: < INR 4,500 |

---

## 7. Simulation Without Physical Hardware

When physical sensors or modules are unavailable, build a **clearly labeled mock or simulation adapter**:

- **Mock sensor generator:** Python script that produces synthetic sensor payloads with configurable drift, noise, and fault patterns. Output format matches real MQTT payload.
- **ED cell model:** `recovered_ca_mg = k * current * time` where `k` is an empirical constant. Clearly labeled as simulation.
- **Filter volume simulator:** `operating_vol += flow_rate * dt`. Clearly labeled.
- **UV254 → DOC curve:** `doc_mgL = a * exp(b * uv254_abs)`. Clearly labeled as proxy correlation, not direct measurement.

All simulation adapters must:
1. Produce output in the same MQTT topic/format as real hardware.
2. Be clearly labeled as `simulation-mode` in code and logs.
3. Not be committed as default behavior; require a build flag or env var to enable.
4. Include documentation steps for real hardware integration.

---
*End of HARDWARE_INTEGRATION.md*