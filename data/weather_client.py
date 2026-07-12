"""Open-Meteo historical weather client with population-weighted HDD/CDD.

Docs: https://open-meteo.com/en/docs/historical-weather-api
No API key required.
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HDD_CDD_BASE_TEMP_C = 18.0

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2

# Representative population centres per country used to population-weight
# a national temperature estimate. Weights are approximate shares of each
# country's population attributed to the surrounding region, and need not
# sum precisely to 1.0 across a country's rows so long as they are
# internally consistent (they are renormalized before use).
COUNTRY_WEATHER_STATIONS: dict[str, list[dict]] = {
    "DE": [
        {"city": "Berlin", "lat": 52.52, "lon": 13.41, "weight": 0.18},
        {"city": "Hamburg", "lat": 53.55, "lon": 9.99, "weight": 0.10},
        {"city": "Munich", "lat": 48.14, "lon": 11.58, "weight": 0.15},
        {"city": "Cologne", "lat": 50.94, "lon": 6.96, "weight": 0.13},
        {"city": "Frankfurt", "lat": 50.11, "lon": 8.68, "weight": 0.10},
        {"city": "Stuttgart", "lat": 48.78, "lon": 9.18, "weight": 0.10},
        {"city": "Dortmund", "lat": 51.51, "lon": 7.47, "weight": 0.10},
        {"city": "Leipzig", "lat": 51.34, "lon": 12.37, "weight": 0.07},
        {"city": "Dresden", "lat": 51.05, "lon": 13.74, "weight": 0.07},
    ],
    "FR": [
        {"city": "Paris", "lat": 48.85, "lon": 2.35, "weight": 0.30},
        {"city": "Marseille", "lat": 43.30, "lon": 5.37, "weight": 0.12},
        {"city": "Lyon", "lat": 45.76, "lon": 4.84, "weight": 0.12},
        {"city": "Toulouse", "lat": 43.60, "lon": 1.44, "weight": 0.10},
        {"city": "Nice", "lat": 43.70, "lon": 7.27, "weight": 0.08},
        {"city": "Nantes", "lat": 47.22, "lon": -1.55, "weight": 0.08},
        {"city": "Strasbourg", "lat": 48.58, "lon": 7.75, "weight": 0.08},
        {"city": "Lille", "lat": 50.63, "lon": 3.06, "weight": 0.12},
    ],
    "NL": [
        {"city": "Amsterdam", "lat": 52.37, "lon": 4.90, "weight": 0.25},
        {"city": "Rotterdam", "lat": 51.92, "lon": 4.48, "weight": 0.20},
        {"city": "The Hague", "lat": 52.08, "lon": 4.31, "weight": 0.15},
        {"city": "Utrecht", "lat": 52.09, "lon": 5.12, "weight": 0.15},
        {"city": "Eindhoven", "lat": 51.44, "lon": 5.48, "weight": 0.15},
        {"city": "Groningen", "lat": 53.22, "lon": 6.57, "weight": 0.10},
    ],
    "BE": [
        {"city": "Brussels", "lat": 50.85, "lon": 4.35, "weight": 0.30},
        {"city": "Antwerp", "lat": 51.22, "lon": 4.40, "weight": 0.25},
        {"city": "Ghent", "lat": 51.05, "lon": 3.72, "weight": 0.15},
        {"city": "Charleroi", "lat": 50.41, "lon": 4.44, "weight": 0.15},
        {"city": "Liege", "lat": 50.63, "lon": 5.57, "weight": 0.15},
    ],
    "IT": [
        {"city": "Rome", "lat": 41.90, "lon": 12.50, "weight": 0.18},
        {"city": "Milan", "lat": 45.46, "lon": 9.19, "weight": 0.20},
        {"city": "Naples", "lat": 40.85, "lon": 14.27, "weight": 0.15},
        {"city": "Turin", "lat": 45.07, "lon": 7.69, "weight": 0.12},
        {"city": "Palermo", "lat": 38.12, "lon": 13.36, "weight": 0.10},
        {"city": "Bologna", "lat": 44.49, "lon": 11.34, "weight": 0.10},
        {"city": "Florence", "lat": 43.77, "lon": 11.26, "weight": 0.08},
        {"city": "Venice", "lat": 45.44, "lon": 12.33, "weight": 0.07},
    ],
    "UK": [
        {"city": "London", "lat": 51.51, "lon": -0.13, "weight": 0.27},
        {"city": "Birmingham", "lat": 52.48, "lon": -1.90, "weight": 0.13},
        {"city": "Manchester", "lat": 53.48, "lon": -2.24, "weight": 0.13},
        {"city": "Leeds", "lat": 53.80, "lon": -1.55, "weight": 0.10},
        {"city": "Glasgow", "lat": 55.86, "lon": -4.25, "weight": 0.10},
        {"city": "Liverpool", "lat": 53.41, "lon": -2.98, "weight": 0.08},
        {"city": "Newcastle", "lat": 54.98, "lon": -1.61, "weight": 0.08},
        {"city": "Bristol", "lat": 51.45, "lon": -2.59, "weight": 0.11},
    ],
}


class WeatherClient:
    """Open-Meteo historical weather client with population-weighted HDD/CDD."""

    def __init__(self, base_url: str = ARCHIVE_URL, session: requests.Session | None = None):
        self.base_url = base_url
        self.session = session or requests.Session()

    def _get(self, params: dict) -> dict:
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(self.base_url, params=params, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"retryable status {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                last_exc = exc
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
        raise RuntimeError(f"Open-Meteo request failed after {MAX_RETRIES} attempts") from last_exc

    def get_daily_temperature(self, lat: float, lon: float, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch daily mean temperature for a single point."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": "temperature_2m_mean",
            "timezone": "auto",
        }
        payload = self._get(params)
        daily = payload.get("daily", {})
        if not daily:
            return pd.DataFrame()
        return pd.DataFrame(
            {
                "date": pd.to_datetime(daily["time"]).date,
                "temperature_mean_c": daily["temperature_2m_mean"],
            }
        )

    def get_country_temperature(self, country_code: str, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch population-weighted national mean temperature for a country.

        Combines several representative city stations, weighting each by
        its approximate population share (see COUNTRY_WEATHER_STATIONS).
        """
        stations = COUNTRY_WEATHER_STATIONS.get(country_code)
        if not stations:
            raise ValueError(f"No weather stations configured for country {country_code}")

        total_weight = sum(s["weight"] for s in stations)
        frames = []
        for station in stations:
            df = self.get_daily_temperature(station["lat"], station["lon"], start_date, end_date)
            if df.empty:
                continue
            df["weight"] = station["weight"] / total_weight
            df["city"] = station["city"]
            frames.append(df)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined["weighted_temp"] = combined["temperature_mean_c"] * combined["weight"]
        national = (
            combined.groupby("date", as_index=False)
            .agg(temperature_mean_c=("weighted_temp", "sum"), weight_sum=("weight", "sum"))
        )
        # Normalize in case a station's data was missing for some dates.
        national["temperature_mean_c"] = national["temperature_mean_c"] / national["weight_sum"]
        national = national.drop(columns="weight_sum")
        national["country_code"] = country_code
        return national


def calculate_hdd_cdd(temperature_df: pd.DataFrame, base_temp_c: float = HDD_CDD_BASE_TEMP_C) -> pd.DataFrame:
    """Add HDD/CDD columns to a DataFrame with a `temperature_mean_c` column.

    HDD (Heating Degree Days) = max(0, base_temp - mean_temp)
    CDD (Cooling Degree Days) = max(0, mean_temp - base_temp)
    """
    df = temperature_df.copy()
    df["hdd"] = (base_temp_c - df["temperature_mean_c"]).clip(lower=0)
    df["cdd"] = (df["temperature_mean_c"] - base_temp_c).clip(lower=0)
    return df
