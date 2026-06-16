from unittest.mock import patch
import numpy as np
import pandas as pd
from src import train, config, storage
from src.model import ModeloPico


def _sembrar_datos():
    rng = np.random.default_rng(1)
    horas, obs = [], []
    base = pd.Timestamp("2025-01-01")
    for d in range(40):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in range(17):
            horas.append({"timestamp": f"{fecha}T{h:02d}:00",
                          "temp_c": 24 + h * (pico - 24) / 16,
                          "humedad": 80.0, "nubosidad": 30.0})
        obs.append({"fecha": fecha, "temp_max_c": round(pico, 1)})
    storage.upsert_hourly(horas)
    storage.upsert_observations(obs)


def test_train_entrena_y_guarda_modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    _sembrar_datos()
    # No tocar la red: el backfill incremental se omite en el test.
    with patch("src.train.backfill.correr"):
        train.correr(incremental=False)
    assert config.ruta_modelo().exists()
    modelo = ModeloPico.cargar(config.ruta_modelo())
    fila = {"hora_decision": 12, "doy_sin": 0.1, "doy_cos": 0.1, "mes": 1,
            "max_hasta_ahora": 30, "temp_actual": 30, "temp_lag1": 29,
            "temp_lag2": 28, "temp_lag3": 27, "tasa_subida": 1.0,
            "humedad_actual": 80, "nubosidad_actual": 30, "forecast_max": None}
    p10, p50, p90 = modelo.predecir(fila)
    assert p10 <= p50 <= p90
