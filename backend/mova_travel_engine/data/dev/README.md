# Development data (SYNTHETIC)

Everything in this folder is **synthetic development data** (`"source": "synthetic_dev"`).
It exists only to exercise the engine and its tests. It is **not** real tourism information:
landmark names and rough locations are used for realistic geography; every other value
(fees, hours, ratings, durations, prices) is generated, and restaurants/hotels are fictional.

Regenerate: `python scripts/generate_dev_data.py --force`
Never place real data here, and never copy this data into `data/raw/`.
