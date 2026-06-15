from datetime import date, timedelta
from pathlib import Path

from src import config, evaluate, export, scraper, storage
from src.model import Predictor

RUTA_DATA_JSON = Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _ultima_fecha(observaciones) -> date:
    if len(observaciones) == 0:
        return config.FECHA_INICIO
    return date.fromisoformat(observaciones["fecha"].max())


def correr(hoy: date | None = None) -> None:
    hoy = hoy or date.today()

    # 1. Recolectar desde el día siguiente al último observado hasta ayer
    observaciones = storage.read_observations()
    desde = _ultima_fecha(observaciones) + timedelta(days=1)
    hasta = hoy - timedelta(days=1)
    if desde <= hasta:
        nuevos = scraper.obtener_observaciones(desde, hasta)
        if nuevos:
            storage.upsert_observations(nuevos)
            observaciones = storage.read_observations()

    # 2. Evaluar predicciones pasadas contra lo observado
    predicciones = storage.read_predictions()
    evaluacion = evaluate.evaluar(predicciones, observaciones)
    storage.write_evaluation(evaluacion)

    # 3. Ajustar el modelo y predecir el horizonte
    modelo = Predictor().ajustar(observaciones, evaluacion)
    fechas_fut = [hoy + timedelta(days=i) for i in range(1, config.HORIZONTE_DIAS + 1)]
    valores = modelo.predecir(fechas_fut)
    filas = [{
        "fecha_prediccion": hoy.isoformat(),
        "fecha_objetivo": f.isoformat(),
        "temp_max_pred_c": v,
        "modelo_version": config.MODELO_VERSION,
    } for f, v in zip(fechas_fut, valores)]
    storage.upsert_predictions(filas)
    predicciones = storage.read_predictions()

    # 4. Exportar para el dashboard
    payload = export.construir_payload(observaciones, predicciones, evaluacion,
                                       hoy=hoy.isoformat())
    export.exportar(RUTA_DATA_JSON, payload)


if __name__ == "__main__":
    correr()
