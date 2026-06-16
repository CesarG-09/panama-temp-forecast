from datetime import date
from unittest.mock import patch
import numpy as np
import pandas as pd
from src import predict, storage, train


def _sembrar_y_entrenar():
    rng = np.random.default_rng(2)
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
    with patch("src.train.backfill.correr"):
        train.correr(incremental=False)


def test_predict_registra_prediccion_de_hoy(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(predict, "RUTA_DATA_JSON", tmp_path / "data.json")
    _sembrar_y_entrenar()

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    preds = storage.read_predictions()
    assert len(preds) == 1
    fila = preds.iloc[0]
    assert fila["fecha_objetivo"] == "2026-06-16"
    assert fila["hora_decision"] == 10
    assert fila["p10"] <= fila["pico_pred"] <= fila["p90"]


def test_predict_fuera_de_franja_no_registra(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    _sembrar_y_entrenar()
    hoy = date(2026, 6, 16)
    with patch("src.predict._hora_local", return_value=3):
        predict.correr(hoy=hoy)
    assert len(storage.read_predictions()) == 0
