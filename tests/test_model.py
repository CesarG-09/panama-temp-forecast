import numpy as np
import pandas as pd
from src import config
from src.model import ModeloPico


def _set_entrenamiento(n_dias=60):
    rng = np.random.default_rng(0)
    filas = []
    base = pd.Timestamp("2025-01-01")
    for d in range(n_dias):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in config.HORAS_DECISION:
            filas.append({
                "fecha_objetivo": fecha, "hora_decision": h,
                "doy_sin": 0.1, "doy_cos": 0.1, "mes": 6,
                "max_hasta_ahora": 24 + h * 0.4,
                "temp_actual": 24 + h * 0.4, "temp_lag1": 24 + (h-1) * 0.4,
                "temp_lag2": 23, "temp_lag3": 23, "tasa_subida": 0.4,
                "humedad_actual": 80, "nubosidad_actual": 30, "forecast_max": pico,
                "target": pico,
            })
    return pd.DataFrame(filas)


def test_ajustar_y_predecir_cuantiles_ordenados():
    df = _set_entrenamiento()
    modelo = ModeloPico().ajustar(df)
    fila = df.iloc[-1].to_dict()
    p10, p50, p90 = modelo.predecir(fila)
    assert p10 <= p50 <= p90
    assert 25 < p50 < 40


def test_persistencia_roundtrip(tmp_path):
    df = _set_entrenamiento()
    modelo = ModeloPico().ajustar(df)
    ruta = tmp_path / "m.txt"
    modelo.guardar(ruta)
    cargado = ModeloPico.cargar(ruta)
    fila = df.iloc[-1].to_dict()
    assert cargado.predecir(fila)[1] == modelo.predecir(fila)[1]
