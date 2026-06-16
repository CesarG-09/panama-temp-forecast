import json
import pandas as pd
from src import export


def test_construir_payload_estructura():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31.5, "p90": 34.5,
         "modelo_version": "gbm-q-v1"},
        {"run_timestamp": "2026-06-16T17:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 12, "pico_pred": 32.8, "p10": 32.2, "p90": 33.4,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-15", "temp_max_c": 32.4}])
    evaluacion = pd.DataFrame([{"fecha_objetivo": "2026-06-15", "hora_decision": 12,
                               "pico_pred": 32.5, "pico_real": 32.4, "error_c": 0.1}])
    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy="2026-06-16")
    assert payload["hoy"] == "2026-06-16"
    # La predicción más reciente de hoy manda el número grande.
    assert payload["pico_hoy"]["pico_pred"] == 32.8
    assert payload["pico_hoy"]["p10"] == 32.2
    assert payload["pico_hoy"]["p90"] == 33.4
    assert len(payload["convergencia_hoy"]) == 2
    assert "error_por_hora" in payload


def test_exportar_escribe_json(tmp_path):
    payload = {"hoy": "2026-06-16", "pico_hoy": None,
               "convergencia_hoy": [], "error_por_hora": []}
    ruta = tmp_path / "data.json"
    export.exportar(ruta, payload)
    assert json.loads(ruta.read_text())["hoy"] == "2026-06-16"
