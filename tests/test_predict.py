import json
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

    # El data.json incluye la curva observada de hoy (horas 0..10).
    datos = json.loads((tmp_path / "data.json").read_text())
    assert len(datos["curva_hoy"]) == 11
    assert datos["curva_hoy"][0] == {"hora": 0, "temp_c": 24.0}
    assert datos["curva_hoy"][-1]["hora"] == 10


def test_predict_curva_usa_wunderground_cuando_hay(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(predict, "RUTA_DATA_JSON", tmp_path / "data.json")
    _sembrar_y_entrenar()

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    # Curva real de MPMG (Wunderground): valores distintos de Open-Meteo y hasta hora 15.
    wu_curva = [{"hora": h, "temp_c": 26.0 + h} for h in range(16)]
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict.wunderground.fetch_curva_intradia", return_value=wu_curva), \
         patch("src.predict.wunderground.fetch_actual", return_value=None), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    datos = json.loads((tmp_path / "data.json").read_text())
    # La curva proviene de MPMG y se recorta a la hora actual (0..10).
    assert len(datos["curva_hoy"]) == 11
    assert datos["curva_hoy"][-1] == {"hora": 10, "temp_c": 36.0}


def test_predict_curva_cae_a_open_meteo_si_wunderground_falla(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(predict, "RUTA_DATA_JSON", tmp_path / "data.json")
    _sembrar_y_entrenar()

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict.wunderground.fetch_curva_intradia",
               side_effect=RuntimeError("sin key")), \
         patch("src.predict.wunderground.fetch_actual",
               side_effect=RuntimeError("sin key")), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    datos = json.loads((tmp_path / "data.json").read_text())
    # Sin Wunderground, la curva cae a Open-Meteo (hora 0 = 24.0) y no hay temp actual.
    assert datos["curva_hoy"][0] == {"hora": 0, "temp_c": 24.0}
    assert len(datos["curva_hoy"]) == 11
    assert datos["temp_actual"] is None


def test_predict_incluye_temp_actual_de_mpmg(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(predict, "RUTA_DATA_JSON", tmp_path / "data.json")
    _sembrar_y_entrenar()

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    actual = {"temp_c": 30.4, "hora_local": "10:20"}
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict.wunderground.fetch_curva_intradia", return_value=[]), \
         patch("src.predict.wunderground.fetch_actual", return_value=actual), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    datos = json.loads((tmp_path / "data.json").read_text())
    assert datos["temp_actual"] == actual


def test_predict_fuera_de_franja_no_registra(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    _sembrar_y_entrenar()
    hoy = date(2026, 6, 16)
    with patch("src.predict._hora_local", return_value=3):
        predict.correr(hoy=hoy)
    assert len(storage.read_predictions()) == 0


def test_horas_pico_cache_rellena_faltantes(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(predict.wunderground, "fetch_horas_pico",
                        lambda desde, hasta: {"2026-06-20": 13, "2026-06-21": 14})
    obs = pd.DataFrame([{"fecha": "2026-06-20", "temp_max_c": 33.0},
                        {"fecha": "2026-06-21", "temp_max_c": 32.0}])
    out = predict._horas_pico_cache(obs)
    assert out == {"2026-06-20": 13, "2026-06-21": 14}
    assert set(storage.read_peak_hours()["fecha"]) == {"2026-06-20", "2026-06-21"}


def test_horas_pico_cache_no_refetch_si_ya_esta(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_peak_hours([{"fecha": "2026-06-20", "hora_pico": 13}])

    def boom(*a, **k):
        raise AssertionError("no debería llamar a la API si ya está cacheado")

    monkeypatch.setattr(predict.wunderground, "fetch_horas_pico", boom)
    obs = pd.DataFrame([{"fecha": "2026-06-20", "temp_max_c": 33.0}])
    assert predict._horas_pico_cache(obs) == {"2026-06-20": 13}
