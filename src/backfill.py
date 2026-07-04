import calendar
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


def _corregir_con_wunderground(desde: date, hasta: date) -> None:
    """Sobreescribe el target derivado de Open-Meteo con la verdad real de la estación MPMG.

    Open-Meteo/ERA5 tiene un sesgo frío sistemático de ~2-3 °C respecto a las
    mediciones reales del aeropuerto porque es un promedio de celda de ~31 km, no
    un dato puntual. Esta función corrige ese sesgo pidiendo los datos mensuales a
    la API de Wunderground y pisando lo que haya en observations.csv. Si la API
    falla (sin clave, límite de tasa, etc.) se mantiene el dato de Open-Meteo para
    ese mes sin interrumpir el resto.
    """
    cursor = desde
    while cursor <= hasta:
        ultimo_dia = calendar.monthrange(cursor.year, cursor.month)[1]
        fin_mes = min(date(cursor.year, cursor.month, ultimo_dia), hasta)
        try:
            obs = wunderground.fetch_via_api(cursor, fin_mes)
            if obs:
                storage.upsert_observations(obs)
                print(f"  Wunderground {cursor}..{fin_mes}: {len(obs)} días corregidos")
        except Exception as e:
            print(f"  Wunderground {cursor}..{fin_mes}: sin corrección ({e})")
        cursor = fin_mes + timedelta(days=1)


def _backfill_mpmg_horario(desde: date, hasta: date) -> None:
    """Llena mpmg_hourly.csv con el horario real de la estación, mes a mes.

    Alimenta las features intradía del modelo (temp_actual_mpmg,
    max_hasta_ahora_mpmg). Un mes que falle (límite de tasa, hueco de la
    estación) se omite con aviso y no interrumpe el resto; re-ejecutar el
    backfill lo completa porque el guardado es upsert por (fecha, hora).
    """
    cursor = desde
    while cursor <= hasta:
        ultimo_dia = calendar.monthrange(cursor.year, cursor.month)[1]
        fin_mes = min(date(cursor.year, cursor.month, ultimo_dia), hasta)
        try:
            filas = wunderground.fetch_horario_rango(cursor, fin_mes)
            if filas:
                storage.upsert_mpmg_hourly(filas)
                print(f"  MPMG horario {cursor}..{fin_mes}: {len(filas)} filas")
        except Exception as e:
            print(f"  MPMG horario {cursor}..{fin_mes}: sin datos ({e})")
        cursor = fin_mes + timedelta(days=1)


def correr(desde: date | None = None, hasta: date | None = None) -> None:
    """Carga histórica: horario de Open-Meteo + pico diario derivado + corrección con MPMG.

    Paso 1 – Open-Meteo (ERA5): descarga rápida del historial horario y deriva el
    pico diario. Evita las ~2.300 cargas día-a-día por navegador de Wunderground.

    Paso 2 – Corrección con Wunderground (API): sobreescribe el target derivado de
    ERA5 con la medición real de la estación MPMG mes a mes. ERA5 tiene un sesgo
    frío de ~2-3 °C respecto al aeropuerto; esta corrección elimina esa diferencia.
    Si la clave WUNDERGROUND_API_KEY no está disponible se omite silenciosamente.

    Además guarda el pronóstico de máxima realmente emitido (Historical Forecast API)
    como feature de entrenamiento.
    """
    desde = desde or config.FECHA_INICIO
    hasta = hasta or (date.today() - timedelta(days=1))

    bloque_ini = desde
    while bloque_ini <= hasta:
        bloque_fin = min(date(bloque_ini.year, 12, 31), hasta)
        print(f"Open-Meteo {bloque_ini}..{bloque_fin}…")
        filas = openmeteo.fetch_archivo(bloque_ini, bloque_fin)
        if filas:
            storage.upsert_hourly(filas)
        _backfill_forecast(bloque_ini, bloque_fin)
        bloque_ini = date(bloque_ini.year + 1, 1, 1)

    storage.upsert_observations(picos_diarios(storage.read_hourly()))

    print("Corrigiendo con datos reales de Wunderground MPMG…")
    _corregir_con_wunderground(desde, hasta)

    print("Descargando horario real de MPMG…")
    _backfill_mpmg_horario(desde, hasta)


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

    try:
        filas_mpmg = wunderground.fetch_horario_rango(desde, hasta)
        if filas_mpmg:
            storage.upsert_mpmg_hourly(filas_mpmg)
    except Exception:
        pass  # sin API las features MPMG de esos días quedan NaN


if __name__ == "__main__":
    desde = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    correr(desde=desde)
