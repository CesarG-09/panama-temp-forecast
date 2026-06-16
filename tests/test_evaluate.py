import pandas as pd
from src import evaluate


def test_evaluar_calcula_error_por_hora():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-15T11:00:00", "fecha_objetivo": "2026-06-15",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31, "p90": 35,
         "modelo_version": "gbm-q-v1"},
        {"run_timestamp": "2026-06-15T17:00:00", "fecha_objetivo": "2026-06-15",
         "hora_decision": 12, "pico_pred": 32.5, "p10": 32, "p90": 33,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-15", "temp_max_c": 32.4}])
    ev = evaluate.evaluar(predicciones, observaciones)
    assert len(ev) == 2
    fila12 = ev[ev["hora_decision"] == 12].iloc[0]
    assert fila12["pico_real"] == 32.4
    assert round(fila12["error_c"], 1) == 0.1


def test_evaluar_omite_dias_sin_observacion():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31, "p90": 35,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame(columns=["fecha", "temp_max_c"])
    ev = evaluate.evaluar(predicciones, observaciones)
    assert len(ev) == 0
