# Water-Quality-Prediction-in-Aquaculture-Using-Machine-Learning-Internet-Of-things

An aquaculture water-quality monitoring and analysis prototype for pond samples. The dashboard reads the included workbook, plots pH, temperature, turbidity, and dissolved-oxygen estimates, compares baseline models, and reports data-quality issues.

## Run the dashboard

```powershell
python -m pip install -r requirements.txt
python -m streamlit run aquasensepro/app.py
```

Streamlit prints the local URL when the dashboard starts. By default it reads `major project Final excel no.1.xlsx`. Use the sidebar to upload another `.csv` or `.xlsx` file with sample ID, pH, temperature, and turbidity columns.

## Data and model notes

- The supplied workbook contains repeated logger rows and 100 grouped sample records. The dashboard reports unkeyed readings separately from incomplete sample groups.
- Dissolved oxygen and the composite water-quality score are derived using the empirical equations in the supplied paper. They are estimates, not direct DO measurements or validated safety classifications.
- Cross-validation uses shuffled folds to compare model reconstruction. The current workbook has no timestamps or independent target labels, so these metrics are not future-condition forecast performance.
- The Arduino sketch reads pH, temperature, and turbidity locally. Live telemetry is not connected to the dashboard.

## Tests

```powershell
python tests/test_aquaculture.py
python tests/test_water_quality.py
```
