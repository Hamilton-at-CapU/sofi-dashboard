# Sofi Dashboard

An interactive Shiny for Python dashboard. *(Update this description.)*

## Live App

Deployed via Shinylive at the project's GitHub Pages URL.

## Features

- *(Add features here)*

## Project Structure

```
sofi-dashboard/
├── app/
│   ├── app.py          # Shiny app
│   ├── data.json       # Pre-processed data used by the app
│   └── styles.css      # Custom CSS
├── data_prep/
│   ├── prep.py         # Data extraction and processing script
│   ├── data.json       # Output from prep.py (copied to app/)
│   └── raw_data/       # Raw data files (not included in GitHub)
├── docs/               # Shinylive build output (GitHub Pages)
├── config.py
├── pyproject.toml
└── requirements.txt
```

## Data Sources

*(Describe your data sources here.)*

## Updating the Data

1. Place raw data files into `data_prep/raw_data/`
2. Run the prep script:
   ```
   python data_prep/prep.py
   ```
3. Copy the output to the app:
   ```
   cp data_prep/data.json app/data.json
   ```

## Running Locally

Install dependencies and run the app:

```
uv run
shiny run app/app.py
```

## Dependencies

| Package | Purpose |
|---|---|
| shiny | App framework |
| shinywidgets | Plotly widget integration |
| plotly | Interactive charts |
| pandas | Data manipulation |
| numpy | Numerical operations |
| openpyxl / xlrd | Reading raw Excel files in prep.py |

## License

See [LICENSE](LICENSE).
