import json

import numpy as np
import pandas as pd
from src import config, model
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
                "temp_actual_mpmg": 24 + h * 0.4,
                "max_hasta_ahora_mpmg": 24 + h * 0.4,
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


def test_q_hat_ensancha_el_intervalo():
    set_ent = _set_entrenamiento()
    m = ModeloPico().ajustar(set_ent)
    fila = set_ent.iloc[0].to_dict()
    p10_a, p50_a, p90_a = m.predecir(fila)
    m.q_hat = 0.7
    p10_b, p50_b, p90_b = m.predecir(fila)
    assert p10_b == round(p10_a - 0.7, 1)
    assert p90_b == round(p90_a + 0.7, 1)
    assert p50_b == p50_a


def test_guardar_cargar_persiste_q_hat(tmp_path):
    set_ent = _set_entrenamiento()
    m = ModeloPico().ajustar(set_ent)
    m.q_hat = 0.4
    m.guardar(tmp_path / "modelo.txt")
    m2 = ModeloPico.cargar(tmp_path / "modelo.txt")
    assert m2.q_hat == 0.4


def test_cargar_modelo_v1_sin_calibracion(tmp_path):
    # Un archivo v1 solo trae los tres boosters; q_hat debe quedar en 0.
    set_ent = _set_entrenamiento()
    m = ModeloPico().ajustar(set_ent)
    ruta = tmp_path / "modelo.txt"
    m.guardar(ruta)
    payload = json.loads(ruta.read_text())
    payload.pop("calibracion")
    ruta.write_text(json.dumps(payload))
    m2 = ModeloPico.cargar(ruta)
    assert m2.q_hat == 0.0


def test_entrenar_calibrado_calcula_q_hat():
    set_ent = _set_entrenamiento(n_dias=120)
    m = model.entrenar_calibrado(set_ent, dias_calibracion=30)
    assert isinstance(m.q_hat, float)
    # Con pocos días no hay split posible: sin calibración.
    m_chico = model.entrenar_calibrado(
        set_ent.head(len(config.HORAS_DECISION) * 10), dias_calibracion=30)
    assert m_chico.q_hat == 0.0
