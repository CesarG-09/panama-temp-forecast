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
