from datetime import date

import requests

from src import config

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HIST_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
_TIMEOUT = 60
_HOURLY_VARS = "temperature_2m,relative_humidity_2m,cloud_cover"


def parse_horario(payload: dict) -> list[dict]:
    """Convierte la respuesta `hourly` de Open-Meteo en filas; omite temp nula."""
    h = payload.get("hourly", {})
    tiempos = h.get("time", [])
    temps = h.get("temperature_2m", [])
    hums = h.get("relative_humidity_2m", [])
    nubes = h.get("cloud_cover", [])
    filas = []
    for i, ts in enumerate(tiempos):
        if temps[i] is None:
            continue
        filas.append({
            "timestamp": ts,
            "temp_c": float(temps[i]),
            "humedad": float(hums[i]) if hums[i] is not None else None,
            "nubosidad": float(nubes[i]) if nubes[i] is not None else None,
        })
    return filas


def parse_forecast_max_diario(payload: dict) -> list[dict]:
    """Convierte la respuesta `daily.temperature_2m_max` en filas {fecha, forecast_max}."""
    d = payload.get("daily", {})
    fechas = d.get("time", [])
    maxs = d.get("temperature_2m_max", [])
    filas = []
    for i, f in enumerate(fechas):
        if i < len(maxs) and maxs[i] is not None:
            filas.append({"fecha": f, "forecast_max": float(maxs[i])})
    return filas


def fetch_archivo(desde: date, hasta: date) -> list[dict]:
    """Histórico horario [desde, hasta] desde el archivo ERA5 de Open-Meteo."""
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "start_date": desde.isoformat(),
        "end_date": hasta.isoformat(),
        "hourly": _HOURLY_VARS,
        "timezone": config.TZ,
    }
    resp = requests.get(ARCHIVE_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_horario(resp.json())


def fetch_forecast_max_historico(desde: date, hasta: date) -> list[dict]:
    """Pronóstico de máxima diaria realmente emitido en el pasado [desde, hasta].

    Usa la Historical Forecast API de Open-Meteo (archivo de los pronósticos
    históricos), de modo que el `forecast_max` de entrenamiento es del mismo
    tipo (un pronóstico con su error real) que el que se usa en vivo. La API
    no cubre los años más tempranos; el llamador tolera que falte.
    """
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "daily": "temperature_2m_max",
        "timezone": config.TZ,
        "start_date": desde.isoformat(),
        "end_date": hasta.isoformat(),
    }
    resp = requests.get(HIST_FORECAST_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_forecast_max_diario(resp.json())


def fetch_intradia(hoy: date) -> list[dict]:
    """Horario de hoy (y ayer) desde la API de forecast con past_days."""
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "hourly": _HOURLY_VARS,
        "timezone": config.TZ,
        "past_days": 1,
        "forecast_days": 1,
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    filas = parse_horario(resp.json())
    hoy_iso = hoy.isoformat()
    return [f for f in filas if f["timestamp"].startswith(hoy_iso)]


def fetch_forecast_max(hoy: date) -> float | None:
    """Máxima diaria pronosticada por Open-Meteo para hoy (feature)."""
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "daily": "temperature_2m_max",
        "timezone": config.TZ,
        "start_date": hoy.isoformat(),
        "end_date": hoy.isoformat(),
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    vals = daily.get("temperature_2m_max", [])
    return float(vals[0]) if vals and vals[0] is not None else None
