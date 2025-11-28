import requests
import pandas as pd


class TransportAPI:
    """
    Simple wrapper around a public transport API.
    Fetches live train/bus data and extracts delays per stop.

    Output format for delays:
        stop_id, delay_minutes
    """

    BASE_URL = "https://api.deutschebahn.com/timetables/v1"   # example placeholder

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    # -------------------------------------------------------------
    # 1. Fetch real-time data for a given city
    # -------------------------------------------------------------
    def get_city_data(self, city: str):
        """
        This function should call your real DB API.
        For now, it uses a mock request structure.
        Replace with the API you actually use.
        """
        try:
            url = f"https://transport.example.com/api?city={city}"
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    # -------------------------------------------------------------
    # 2. Extract delays from API response
    # -------------------------------------------------------------
    def parse_delays(self, data: dict) -> pd.DataFrame:
        """
        Extract delays per station from API raw JSON.

        Expected format inside JSON:
            {
              "trains": [
                  { "stop_id": "...", "delay": 4 },
                  { "stop_id": "...", "delay": 7 }
              ]
            }

        If your real API has different structure, adjust here.
        """

        if data is None or "trains" not in data:
            # empty fallback
            return pd.DataFrame({
                "stop_id": [],
                "delay_minutes": []
            })

        records = []

        for train in data["trains"]:
            stop = train.get("stop_id")
            delay = train.get("delay", 0)

            if stop is None:
                continue

            records.append({
                "stop_id": stop,
                "delay_minutes": delay
            })

        return pd.DataFrame(records)
