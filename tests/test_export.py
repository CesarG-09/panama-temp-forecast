import json
import math

import pandas as pd

from src import export


def test_construir_payload_tiene_secciones_esperadas():
    observaciones = pd.DataFrame({"fecha": ["2021-05-31"], "temp_max_c": [30.0]})
    predicciones = pd.DataFrame({
        "fecha_prediccion": ["2021-05-31"], "fecha_objetivo": ["2021-06-01"],
        "temp_max_pred_c": [31.0], "modelo_version": ["clima-v1"],
    })
    evaluacion = pd.DataFrame({
        "fecha_objetivo": ["2021-05-31"], "pred_c": [29.5], "real_c": [30.0],
        "error_c": [-0.5], "acierto": [True],
    })

    payload = export.construir_payload(observaciones, predicciones, evaluacion, hoy="2021-05-31")

    assert payload["historico"] == [{"fecha": "2021-05-31", "temp_max_c": 30.0}]
    assert payload["predicciones"] == [{"fecha_objetivo": "2021-06-01", "temp_max_pred_c": 31.0}]
    assert payload["metricas"]["aciertos_pct"] == 100.0
    assert "generado" in payload


def test_exportar_escribe_json(tmp_path):
    ruta = tmp_path / "data.json"
    export.exportar(ruta, {"historico": [], "predicciones": [], "metricas": {},
                          "evaluaciones": [], "generado": "x"})
    datos = json.loads(ruta.read_text())
    assert datos["generado"] == "x"


def test_exportar_sanea_nan_a_null_en_arranque_en_frio(tmp_path):
    # En arranque en frío el modelo devuelve NaN; el JSON debe seguir siendo válido
    ruta = tmp_path / "data.json"
    payload = {
        "generado": "x",
        "historico": [],
        "predicciones": [{"fecha_objetivo": "2026-06-15", "temp_max_pred_c": math.nan}],
        "metricas": {"n": 0, "mae": None, "aciertos_pct": None},
        "evaluaciones": [],
    }
    export.exportar(ruta, payload)
    datos = json.loads(ruta.read_text())  # no debe lanzar
    assert datos["predicciones"][0]["temp_max_pred_c"] is None
