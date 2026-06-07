"""
Data preparation script.

1. Place raw data files into data_prep/raw_data/
2. Run:  python data_prep/prep.py
3. Copy output to app:  cp data_prep/data.json app/data.json
"""

import json
from pathlib import Path

RAW_DATA_DIR = Path(__file__).parent / "raw_data"
OUTPUT_PATH = Path(__file__).parent / "data.json"


def load_raw() -> list[dict]:
    """Load and clean raw data files. Edit this function for your data sources."""
    records = []
    # TODO: load your raw data here
    # e.g. pd.read_excel(RAW_DATA_DIR / "your_file.xlsx")
    return records


def main():
    records = load_raw()
    with open(OUTPUT_PATH, "w") as f:
        json.dump(records, f, indent=2)
    print(f"Wrote {len(records)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
