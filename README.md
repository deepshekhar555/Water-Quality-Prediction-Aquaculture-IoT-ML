# AquaSense Pro & ReGen-X / Aquaculture Analytics

This repository contains two separate software workflows: a purifier telemetry prototype dashboard for AquaSense Pro & ReGen-X, and the original aquaculture pond-sample analytics dashboard. The purifier dashboard supports CSV review and clearly labeled simulated demo data; it does not connect to live hardware or establish drinking-water safety.

## Purifier prototype dashboard

```powershell
python -m pip install -r requirements.txt
python -m streamlit run aquasensepro/purifier_app.py
```

The main page shows three source options: **Live USB**, **Upload CSV**, and **Simulation**. Live USB reads the included sketch's CSV stream at 9600 baud. Connect the board and use the visible port controls; the sketch provides sample ID, uptime, pH, temperature, and firmware-mapped turbidity only. For a populated upload, use `purifier_telemetry_demo_simulated.csv` or the **Sample CSV · simulated** download; all 12 rows are explicitly marked simulated. The empty template is for adding your own measured rows. Simulation scenarios exercise nominal, pressure-trip, sensor-range, and flow-imbalance alarms, but are not hardware evidence.

## Original aquaculture dashboard

```powershell
python -m streamlit run aquasensepro/app.py
```

This dashboard analyzes the included aquaculture workbook. It is not the purifier monitor and does not connect to live sensors.

## Tests

```powershell
python -m unittest discover -s tests -p "test_purifier_monitoring.py"
python -m unittest discover -s tests -p "test_serial_telemetry.py"
python tests/test_foundation.py
python tests/test_rul_pipeline.py
python tests/test_aquaculture.py
python tests/test_water_quality.py
```

## Prototype evidence boundary

Software simulations, uploaded telemetry, and dashboard alarms are not evidence of physical RO recovery, electrodialysis mineral recovery, calibrated sensor performance, tested safety interlocks, or drinking-water safety. RUL estimates require a real, documented, chronologically held-out dataset before any accuracy claim.
