from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, evaluate, export, features, storage
from src.model import ModeloPico
from src.sources import openmeteo

RUTA_DATA_JSON = Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _hora_local(hoy: date) -> int:
    return datetime.now(ZoneInfo(config.TZ)).hour


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

    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy=hoy.isoformat())
    export.exportar(RUTA_DATA_JSON, payload)


if __name__ == "__main__":
    correr()
