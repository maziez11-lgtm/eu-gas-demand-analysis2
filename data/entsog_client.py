"""Client for the ENTSOG Transparency Platform API.

Docs: https://transparency.entsog.eu/api/v1
No API key required for public operational data endpoints.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests

BASE_URL = "https://transparency.entsog.eu/api/v1"

# ENTSOG country codes for the demand-side markets we track.
COUNTRIES = ["DE", "FR", "NL", "BE", "IT"]

# Physical flow indicator as defined by ENTSOG's operationalData endpoint.
INDICATOR_PHYSICAL_FLOW = "Physical Flow"

DEFAULT_TIMEOUT = 30
DEFAULT_PAGE_SIZE = 300
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2


class EntsogClient:
    """Thin wrapper around the ENTSOG operationalData REST endpoint.

    Handles pagination (ENTSOG paginates via `page`/`size` query params)
    and retries transient failures (5xx, timeouts, connection errors)
    with exponential backoff.
    """

    def __init__(self, base_url: str = BASE_URL, session: requests.Session | None = None):
        self.base_url = base_url
        self.session = session or requests.Session()

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.base_url}{path}"
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"retryable status {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                last_exc = exc
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))
        raise RuntimeError(f"ENTSOG request failed after {MAX_RETRIES} attempts: {url}") from last_exc

    def _paginate(self, path: str, params: dict) -> list[dict]:
        results: list[dict] = []
        page = 0
        while True:
            page_params = {**params, "page": page, "size": DEFAULT_PAGE_SIZE}
            payload = self._get(path, page_params)
            batch = payload.get("operationalData", payload.get("data", []))
            if not batch:
                break
            results.extend(batch)
            if len(batch) < DEFAULT_PAGE_SIZE:
                break
            page += 1
        return results

    def get_physical_flows(
        self,
        country_code: str,
        start_date: date,
        end_date: date,
        indicator: str = INDICATOR_PHYSICAL_FLOW,
    ) -> pd.DataFrame:
        """Fetch daily physical flow operational data for a country.

        Returns a DataFrame with (at least) columns: period, pointKey,
        pointLabel, directionKey, value, unit.
        """
        params = {
            "countryCode": country_code,
            "indicator": indicator,
            "periodType": "day",
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
        }
        records = self._paginate("/operationalData", params)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame.from_records(records)
        if "periodFrom" in df.columns:
            df["period"] = pd.to_datetime(df["periodFrom"]).dt.date
        return df

    def get_physical_flows_multi(
        self,
        countries: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch physical flows for multiple countries, concatenated."""
        frames = []
        for country in countries:
            df = self.get_physical_flows(country, start_date, end_date)
            if not df.empty:
                df["queryCountry"] = country
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def get_latest_available_date(self, country_code: str = "DE") -> date:
        """Probe ENTSOG for the most recent date with published data.

        ENTSOG typically publishes with a 1-2 day lag. We check the last
        7 days and return the most recent date that returned data.
        """
        today = date.today()
        for lag in range(1, 8):
            candidate = today - timedelta(days=lag)
            df = self.get_physical_flows(country_code, candidate, candidate)
            if not df.empty:
                return candidate
        raise RuntimeError(f"No ENTSOG data found for {country_code} in the last 7 days")


def resolve_analysis_date(analysis_date: date | str | None, client: EntsogClient | None = None) -> date:
    """Resolve ANALYSIS_DATE: if None, auto-resolve to the latest available data point."""
    if analysis_date is None:
        client = client or EntsogClient()
        return client.get_latest_available_date()
    if isinstance(analysis_date, str):
        return datetime.strptime(analysis_date, "%Y-%m-%d").date()
    return analysis_date
