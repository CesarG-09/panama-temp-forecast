from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, evaluate, export, features, storage
from src.model import ModeloPico
from src.sources import openmeteo, wunderground

RUTA_DATA_JSON = Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _hora_local(hoy: date) -> int:
    return datetime.now(ZoneInfo(config.TZ)).hour


def _curva_observada(intradia: pd.DataFrame, hora: int) -> list[dict]:
    """Temperatura de hoy hora a hora (Open-Meteo), solo hasta la hora actual.

    Respaldo cuando la estación MPMG no responde; ver `_curva_observada_mpmg`.
    """
    filas = []
    for _, r in intradia.sort_values("timestamp").iterrows():
        h = int(r["timestamp"][11:13])
        if h <= hora:
            filas.append({"hora": h, "temp_c": round(float(r["temp_c"]), 1)})
    return filas


def _curva_observada_mpmg(fecha: date, hora: int) -> list[dict] | None:
    """Curva horaria observada de hoy desde la estación real MPMG (Wunderground).

    Es la misma fuente que la tabla horaria de wunderground.com, así el dashboard
    coincide con lo que el usuario ve allí. Devuelve None si la API no responde
    (sin clave, error de red…) para que el llamador caiga a Open-Meteo.
    """
    try:
        curva = wunderground.fetch_curva_intradia(fecha)
    except Exception:
        return None
    return [c for c in curva if c["hora"] <= hora]


def _temp_actual_mpmg(fecha: date) -> dict | None:
    """Temperatura actual de la estación MPMG; None si la API no responde."""
    try:
        return wunderground.fetch_actual(fecha)
    except Exception:
        return None


def _horas_pico_cache(observaciones: pd.DataFrame, dias: int = 25) -> dict:
    """Rellena (lazy) y devuelve el cache fecha->hora_pico de los últimos `dias`
    días observados. Una sola llamada de rango a Wunderground para los faltantes;
    si falla, deja el cache como está (se reintenta la próxima corrida).
    """
    cache = storage.read_peak_hours()
    conocidas = set(cache["fecha"].astype(str))
    recientes = [str(f) for f in observaciones.tail(dias)["fecha"]]
    faltantes = sorted(f for f in recientes if f not in conocidas)
    if faltantes:
        try:
            nuevas = wunderground.fetch_horas_pico(
                date.fromisoformat(faltantes[0]), date.fromisoformat(faltantes[-1]))
            faltantes_set = set(faltantes)
            filas = [{"fecha": f, "hora_pico": int(h)}
                     for f, h in nuevas.items() if f in faltantes_set]
            if filas:
                storage.upsert_peak_hours(filas)
                cache = storage.read_peak_hours()
        except Exception:
            pass
    return {str(r["fecha"]): int(r["hora_pico"]) for _, r in cache.iterrows()}


def correr(hoy: date | None = None) -> None:
    hoy = hoy or datetime.now(ZoneInfo(config.TZ)).date()
    hora = _hora_local(hoy)

    # 1. Solo se predice dentro de la franja diurna de decisión.
    if hora not in config.HORAS_DECISION:
        return

    # 2. Intradía + forecast de hoy.
    intradia = pd.DataFrame(openmeteo.fetch_intradia(hoy))
    forecast_max = openmeteo.fetch_forecast_max(hoy)
    if len(intradia) == 0:
        return

    # 3. Features y predicción.
    fila = features.construir_fila(intradia, fecha=hoy.isoformat(),
                                   hora_h=hora, forecast_max=forecast_max)
    modelo = ModeloPico.cargar(config.ruta_modelo())
    p10, p50, p90 = modelo.predecir(fila)

    storage.append_prediction({
        "run_timestamp": datetime.now(ZoneInfo(config.TZ)).isoformat(timespec="seconds"),
        "fecha_objetivo": hoy.isoformat(),
        "hora_decision": hora,
        "pico_pred": p50,
        "p10": p10,
        "p90": p90,
        "modelo_version": config.MODELO_VERSION,
    })

    # 4. Evaluar días ya cerrados y exportar dashboard.
    predicciones = storage.read_predictions()
    observaciones = storage.read_observations()
    evaluacion = evaluate.evaluar(predicciones, observaciones)
    storage.write_evaluation(evaluacion)

    # La curva y la temperatura actual salen de la estación real MPMG
    # (Wunderground) para que coincidan con su página; si la API falla, la
    # curva cae a Open-Meteo y la temperatura actual simplemente no se muestra.
    curva = _curva_observada_mpmg(hoy, hora)
    if curva is None:
        curva = _curva_observada(intradia, hora)
    temp_actual = _temp_actual_mpmg(hoy)
    horas_pico = _horas_pico_cache(observaciones)

    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy=hoy.isoformat(),
                                       curva_hoy=curva, temp_actual=temp_actual,
                                       horas_pico=horas_pico)
    export.exportar(RUTA_DATA_JSON, payload)


if __name__ == "__main__":
    correr()
