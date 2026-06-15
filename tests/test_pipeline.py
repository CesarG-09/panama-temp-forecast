from datetime import date

import pandas as pd

from src import pipeline, storage


def test_pipeline_recolecta_evalua_y_predice(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    # Aísla el data.json del dashboard real durante el test
    monkeypatch.setattr(pipeline, "RUTA_DATA_JSON", tmp_path / "data.json")

    # Histórico previo: 400 días constantes a 30 °C terminando el 2021-05-31
    fechas = pd.date_range(end="2021-05-31", periods=400, freq="D")
    storage.upsert_observations(
        [{"fecha": f.strftime("%Y-%m-%d"), "temp_max_c": 30.0} for f in fechas])

    # El scraper "trae" el día 2021-06-01 observado a 30 °C
    def fake_fetch(desde, hasta):
        return [{"fecha": "2021-06-01", "temp_max_c": 30.0}]

    monkeypatch.setattr(pipeline.scraper, "obtener_observaciones", fake_fetch)

    pipeline.correr(hoy=date(2021, 6, 1))

    preds = storage.read_predictions()
    # Se generaron 7 predicciones desde hoy inclusive (objetivo 06-01 .. 06-07)
    futuras = preds[preds["fecha_prediccion"] == "2021-06-01"]
    assert len(futuras) == 7
    assert "2021-06-01" in set(preds["fecha_objetivo"])  # el día actual sí se predice
    # data.json fue escrito
    assert pipeline.RUTA_DATA_JSON.exists()


def test_pipeline_es_idempotente(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(pipeline, "RUTA_DATA_JSON", tmp_path / "data.json")
    fechas = pd.date_range(end="2021-05-31", periods=400, freq="D")
    storage.upsert_observations(
        [{"fecha": f.strftime("%Y-%m-%d"), "temp_max_c": 30.0} for f in fechas])
    monkeypatch.setattr(pipeline.scraper, "obtener_observaciones",
                        lambda d, h: [{"fecha": "2021-06-01", "temp_max_c": 30.0}])

    pipeline.correr(hoy=date(2021, 6, 1))
    n1 = len(storage.read_predictions())
    pipeline.correr(hoy=date(2021, 6, 1))
    n2 = len(storage.read_predictions())
    assert n1 == n2  # re-correr el mismo día no duplica
