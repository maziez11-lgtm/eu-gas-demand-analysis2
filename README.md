# EU Gas Demand Analysis

Toolkit for tracking and analyzing European natural gas demand: physical
flows from the ENTSOG Transparency Platform (EU), UK demand from National
Gas Transmission (post-Brexit, outside ENTSOG), and weather-normalized
demand via population-weighted heating/cooling degree days.

## Setup

Requires Python 3.14. No virtual environment is used — install
dependencies system-wide with pip:

```bash
pip install pandas requests jupyter pyarrow numpy matplotlib
```

Launch Jupyter and run the notebooks in order:

```bash
jupyter notebook
```

### API keys

The ENTSOG and Open-Meteo endpoints used here do not require API keys.
If you extend this toolkit with a data source that does, place the key
as a plain variable in **cell 0** of the relevant notebook (no `.env`
file, no `python-dotenv`):

```python
# Cell 0
SOME_API_KEY = "..."
```

Never commit real keys — cell 0 in checked-in notebooks should only
contain placeholder values.

### `ANALYSIS_DATE`

Every ingestion notebook defines:

```python
ANALYSIS_DATE = None
```

When `None`, the notebook auto-resolves `ANALYSIS_DATE` to the latest
date with published data available from the source API (ENTSOG
typically publishes with a 1-2 day lag). Set an explicit `date(...)` to
pin a run to a specific historical date instead.

## Structure

```
data/
  entsog_client.py    ENTSOG Transparency Platform API client (physical flows)
  weather_client.py   Open-Meteo historical weather client + HDD/CDD calc
notebooks/
  01_entsog_ingestion.ipynb   Gas flow ingestion: DE, FR, NL, BE, IT -> parquet
  02_uk_ngt_ingestion.ipynb   UK gas demand via National Gas Transmission
  03_hdd_cdd_calc.ipynb       HDD/CDD calc + observed vs weather-normalized demand
```

Parquet exports land in `data/` and are gitignored — re-run the
ingestion notebooks to regenerate them locally.

## Data sources

| Source | Coverage | Auth | Notes |
|---|---|---|---|
| [ENTSOG Transparency Platform](https://transparency.entsog.eu/api/v1) | DE, FR, NL, BE, IT physical flows | None | `operationalData` endpoint, paginated |
| [National Gas Transmission (NGT) Data Portal](https://data.nationalgas.com/) | UK gas demand | None | Post-Brexit UK data sits outside ENTSOG |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | Temperature by city, population-weighted per country | None | Used for HDD/CDD (18°C base) |

## Countries covered

Germany (DE), France (FR), Netherlands (NL), Belgium (BE), Italy (IT), and
the United Kingdom (UK, via NGT).
