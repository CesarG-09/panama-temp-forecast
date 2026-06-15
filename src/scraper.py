import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from src import config

API_URL = "https://api.weather.com/v1/location/{station}/observations/historical.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (panama-temp-forecast)"}
_TIMEOUT = 30


def parse_historical_json(payload: dict) -> list[dict]:
    """Agrupa observaciones por día (hora local de Panamá) y toma el máximo."""
    tz = ZoneInfo(config.TZ)
    por_dia: dict = defaultdict(list)
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dia = datetime.fromtimestamp(ts, tz=tz).date()
        por_dia[dia].append(temp)
    return [
        {"fecha": dia.isoformat(), "temp_max_c": round(max(temps), 1)}
        for dia, temps in sorted(por_dia.items())
    ]


def fetch_via_api(desde, hasta) -> list[dict]:
    """Obtiene observaciones del rango [desde, hasta] vía la API de Weather.com."""
    api_key = os.environ.get("WUNDERGROUND_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno WUNDERGROUND_API_KEY")
    params = {
        "apiKey": api_key,
        "units": "m",
        "startDate": desde.strftime("%Y%m%d"),
        "endDate": hasta.strftime("%Y%m%d"),
    }
    resp = requests.get(API_URL.format(station=config.ESTACION), params=params,
                        headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_historical_json(resp.json())
