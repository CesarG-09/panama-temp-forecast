import sys
from datetime import date, timedelta

import pandas as pd

from src import config, storage
from src.sources import openmeteo, wunderground


def picos_diarios(hourly: pd.DataFrame) -> list[dict]:
    """Pico diario (máximo de las horas) a partir del horario de Open-Meteo."""
    if len(hourly) == 0:
        return []
    df = hourly.copy()
    df["fecha"] = df["timestamp"].str.slice(0, 10)
    g = df.groupby("fecha")["temp_c"].max().reset_index()
    return [{"fecha": r["fecha"], "temp_max_c": round(float(r["temp_c"]), 1)}
            for _, r in g.iterrows()]


def _backfill_forecast(desde: date, hasta: date) -> None:
    """Descarga el pronóstico de máxima histórico y lo guarda; tolera años sin cobertura."""
    try:
        fcst = openmeteo.fetch_forecast_max_historico(desde, hasta)
        if fcst:
            storage.upsert_forecast(fcst)
    except Exception:
        pass  # la Historical Forecast API no cubre los años más tempranos


def correr(desde: date | None = None, hasta: date | None = None) -> None:
    """Carga histórica: horario de Open-Meteo + pico diario derivado + forecast_max.

    El target histórico se deriva del propio archivo horario de Open-Meteo (máximo
    por día), evitando ~2.300 cargas día-a-día por navegador de Wunderground. La
    verdad de la estación MPMG (Wunderground) se superpone en los días recientes
    desde `actualizar_reciente` (lazo en curso). Además guarda el pronóstico de
    máxima realmente emitido (Historical Forecast API) como feature.
    """
    desde = desde or config.FECHA_INICIO
    hasta = hasta or (date.today() - timedelta(days=1))

    bloque_ini = desde
    while bloque_ini <= hasta:
        bloque_fin = min(date(bloque_ini.year, 12, 31), hasta)
        filas = openmeteo.fetch_archivo(bloque_ini, bloque_fin)
        if filas:
            storage.upsert_hourly(filas)
        _backfill_forecast(bloque_ini, bloque_fin)
        bloque_ini = date(bloque_ini.year + 1, 1, 1)

    storage.upsert_observations(picos_diarios(storage.read_hourly()))


def actualizar_reciente(dias: int = 7) -> None:
    """Refresca los últimos `dias` días: horario + pico diario + forecast_max.

    El target reciente usa Open-Meteo como base y, si la API de Wunderground
    responde, lo sobreescribe con el pico real de la estación MPMG (la verdad).
    El navegador de respaldo NO se usa aquí para no colgar el job nocturno.
    """
    hasta = date.today() - timedelta(days=1)
    desde = hasta - timedelta(days=dias)

    filas = openmeteo.fetch_archivo(desde, hasta)
    if filas:
        storage.upsert_hourly(filas)
        storage.upsert_observations(picos_diarios(pd.DataFrame(filas)))

    _backfill_forecast(desde, hasta)

    try:
        obs = wunderground.fetch_via_api(desde, hasta)
        if obs:
            storage.upsert_observations(obs)
    except Exception:
        pass  # si la API falla, queda el target derivado de Open-Meteo


if __name__ == "__main__":
    desde = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    correr(desde=desde)
