import os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

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


def parse_curva_intradia(payload: dict, fecha) -> list[dict]:
    """Temperatura máxima por hora local de `fecha` (lo que Wunderground muestra por hora).

    Agrupa las observaciones por hora en horario de Panamá y toma el máximo de cada
    hora, igual que la tabla horaria del historial diario de Wunderground.
    """
    tz = ZoneInfo(config.TZ)
    fecha_iso = fecha.isoformat()
    por_hora: dict[int, float] = {}
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=tz)
        if dt.date().isoformat() != fecha_iso:
            continue
        if dt.hour not in por_hora or temp > por_hora[dt.hour]:
            por_hora[dt.hour] = float(temp)
    return [{"hora": h, "temp_c": round(por_hora[h], 1)} for h in sorted(por_hora)]


def parse_actual(payload: dict, fecha) -> dict | None:
    """Temperatura actual = última observación (más reciente) de `fecha` en hora local.

    Devuelve {"temp_c", "hora_local"} de la observación con `valid_time_gmt` mayor,
    o None si no hay observaciones de esa fecha. Es la misma fuente (estación MPMG)
    que muestra la página de condiciones actuales de wunderground.com.
    """
    tz = ZoneInfo(config.TZ)
    fecha_iso = fecha.isoformat()
    mejor_ts = None
    resultado = None
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=tz)
        if dt.date().isoformat() != fecha_iso:
            continue
        if mejor_ts is None or ts > mejor_ts:
            mejor_ts = ts
            resultado = {"temp_c": round(float(temp), 1),
                         "hora_local": dt.strftime("%H:%M")}
    return resultado


def parse_horas_pico(payload: dict) -> dict:
    """Hora local (Panamá) del máximo de `temp` por día. Empate -> la más temprana."""
    tz = ZoneInfo(config.TZ)
    mejor: dict = {}  # fecha_iso -> (temp_max, hora)
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=tz)
        fecha = dt.date().isoformat()
        prev = mejor.get(fecha)
        if prev is None or temp > prev[0] or (temp == prev[0] and dt.hour < prev[1]):
            mejor[fecha] = (float(temp), dt.hour)
    return {fecha: hora for fecha, (_, hora) in mejor.items()}


def fetch_horas_pico(desde, hasta) -> dict:
    """Hora del pico (local) por día en [desde, hasta]; una sola llamada a la API."""
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
    return parse_horas_pico(resp.json())


def fetch_curva_intradia(fecha) -> list[dict]:
    """Curva horaria observada de `fecha` desde la estación MPMG (API de Weather.com)."""
    api_key = os.environ.get("WUNDERGROUND_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno WUNDERGROUND_API_KEY")
    params = {
        "apiKey": api_key,
        "units": "m",
        "startDate": fecha.strftime("%Y%m%d"),
        "endDate": fecha.strftime("%Y%m%d"),
    }
    resp = requests.get(API_URL.format(station=config.ESTACION), params=params,
                        headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_curva_intradia(resp.json(), fecha)


def fetch_actual(fecha) -> dict | None:
    """Temperatura actual (última observación de hoy) desde la estación MPMG."""
    api_key = os.environ.get("WUNDERGROUND_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno WUNDERGROUND_API_KEY")
    params = {
        "apiKey": api_key,
        "units": "m",
        "startDate": fecha.strftime("%Y%m%d"),
        "endDate": fecha.strftime("%Y%m%d"),
    }
    resp = requests.get(API_URL.format(station=config.ESTACION), params=params,
                        headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_actual(resp.json(), fecha)


def f_a_c(f: float) -> float:
    return round((f - 32) * 5 / 9, 1)


def parse_history_html(html: str, fecha) -> dict:
    """Extrae la temperatura máxima (°F en la web) de la página de historial diario."""
    soup = BeautifulSoup(html, "lxml")
    for tr in soup.select("tr"):
        celdas = tr.find_all("td")
        if celdas and "High Temp" in celdas[0].get_text():
            valor = tr.select_one(".wu-value")
            f = float(valor.get_text().strip())
            return {"fecha": fecha.isoformat(), "temp_max_c": f_a_c(f)}
    raise ValueError("No se encontró 'High Temp' en el HTML")


def fetch_via_browser(fecha) -> list[dict]:
    """Respaldo: abre la página real en Playwright y lee la máxima del día.

    Requiere `playwright install chromium`. Se usa solo si la API falla.
    """
    from playwright.sync_api import sync_playwright

    url = (f"https://www.wunderground.com/history/daily/pa/panama-city/MPMG/"
           f"date/{fecha.isoformat()}")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(user_agent=_HEADERS["User-Agent"])
        pagina.goto(url, wait_until="networkidle", timeout=60000)
        pagina.wait_for_selector("table.days", timeout=30000)
        html = pagina.content()
        navegador.close()
    return [parse_history_html(html, fecha)]


def obtener_observaciones(desde, hasta) -> list[dict]:
    """Intenta la API; si falla, cae al navegador día por día."""
    try:
        return fetch_via_api(desde, hasta)
    except Exception:
        filas: list[dict] = []
        dia = desde
        while dia <= hasta:
            try:
                filas.extend(fetch_via_browser(dia))
            except Exception:
                pass  # día sin dato: se omite, queda como hueco
            dia += timedelta(days=1)
        return filas
