import pandas as pd
from src import storage


def test_observations_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_observations([{"fecha": "2020-01-01", "temp_max_c": 31.0}])
    storage.upsert_observations([{"fecha": "2020-01-01", "temp_max_c": 32.0},
                                 {"fecha": "2020-01-02", "temp_max_c": 30.0}])
    df = storage.read_observations()
    assert len(df) == 2
    assert df.set_index("fecha").loc["2020-01-01", "temp_max_c"] == 32.0


def test_upsert_y_read_peak_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_peak_hours([{"fecha": "2026-06-20", "hora_pico": 13}])
    storage.upsert_peak_hours([{"fecha": "2026-06-20", "hora_pico": 14},   # reemplaza
                               {"fecha": "2026-06-21", "hora_pico": 15}])
    df = storage.read_peak_hours()
    pares = dict(zip(df["fecha"], df["hora_pico"]))
    assert pares == {"2026-06-20": 14, "2026-06-21": 15}


def test_hourly_history_roundtrip_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_hourly([{"timestamp": "2020-01-01T00:00", "temp_c": 24.0,
                            "humedad": 80.0, "nubosidad": 10.0}])
    storage.upsert_hourly([{"timestamp": "2020-01-01T00:00", "temp_c": 25.0,
                            "humedad": 81.0, "nubosidad": 11.0}])
    df = storage.read_hourly()
    assert len(df) == 1
    assert df.iloc[0]["temp_c"] == 25.0


def test_forecast_roundtrip_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_forecast([{"fecha": "2026-06-10", "forecast_max": 32.0}])
    storage.upsert_forecast([{"fecha": "2026-06-10", "forecast_max": 32.8},
                             {"fecha": "2026-06-11", "forecast_max": 31.0}])
    df = storage.read_forecast()
    assert len(df) == 2
    assert df.set_index("fecha").loc["2026-06-10", "forecast_max"] == 32.8


def test_predictions_append(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    fila = {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
            "hora_decision": 6, "pico_pred": 33.0, "p10": 31.5, "p90": 34.5,
            "modelo_version": "gbm-q-v1"}
    storage.append_prediction(fila)
    storage.append_prediction({**fila, "hora_decision": 7})
    df = storage.read_predictions()
    assert len(df) == 2
    assert set(df.columns) == set(fila.keys())


def test_predictions_upsert_misma_hora(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    fila = {"run_timestamp": "2026-06-17T08:00:00", "fecha_objetivo": "2026-06-17",
            "hora_decision": 8, "pico_pred": 28.6, "p10": 27.4, "p90": 30.1,
            "modelo_version": "gbm-q-v1"}
    storage.append_prediction(fila)
    # Re-corrida en la misma hora: debe reemplazar, no duplicar.
    storage.append_prediction({**fila, "run_timestamp": "2026-06-17T08:30:00",
                               "pico_pred": 29.1})
    df = storage.read_predictions()
    assert len(df) == 1
    assert df.iloc[0]["pico_pred"] == 29.1
    assert df.iloc[0]["run_timestamp"] == "2026-06-17T08:30:00"


def test_evaluation_write_read(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    ev = pd.DataFrame([{"fecha_objetivo": "2026-06-15", "hora_decision": 12,
                        "pico_pred": 33.0, "pico_real": 32.4, "error_c": 0.6}])
    storage.write_evaluation(ev)
    df = storage.read_evaluation()
    assert df.iloc[0]["error_c"] == 0.6


def test_upsert_mpmg_hourly_dedup_por_fecha_hora(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_mpmg_hourly([
        {"fecha": "2026-06-16", "hora": 10, "temp_c": 30.0},
        {"fecha": "2026-06-16", "hora": 11, "temp_c": 31.0},
    ])
    storage.upsert_mpmg_hourly([
        {"fecha": "2026-06-16", "hora": 11, "temp_c": 31.5},  # pisa la anterior
        {"fecha": "2026-06-17", "hora": 9, "temp_c": 29.0},
    ])
    df = storage.read_mpmg_hourly()
    assert len(df) == 3
    fila_11 = df[(df["fecha"] == "2026-06-16") & (df["hora"] == 11)].iloc[0]
    assert fila_11["temp_c"] == 31.5
    assert list(df.columns) == ["fecha", "hora", "temp_c"]
