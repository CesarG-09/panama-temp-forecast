from datetime import date
from unittest.mock import patch
import pandas as pd
from src import backfill, storage


def test_picos_diarios_toma_maximo_por_dia():
    hourly = pd.DataFrame([
        {"timestamp": "2020-01-01T08:00", "temp_c": 26.0, "humedad": 80.0, "nubosidad": 10.0},
        {"timestamp": "2020-01-01T13:00", "temp_c": 31.0, "humedad": 60.0, "nubosidad": 20.0},
        {"timestamp": "2020-01-02T13:00", "temp_c": 30.0, "humedad": 60.0, "nubosidad": 20.0},
    ])
    picos = backfill.picos_diarios(hourly)
    assert picos == [{"fecha": "2020-01-01", "temp_max_c": 31.0},
                     {"fecha": "2020-01-02", "temp_max_c": 30.0}]


def test_backfill_deriva_observaciones_de_open_meteo(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2020-01-01T10:00", "temp_c": 30.0, "humedad": 80.0, "nubosidad": 20.0},
             {"timestamp": "2020-01-01T14:00", "temp_c": 33.0, "humedad": 70.0, "nubosidad": 30.0}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico", return_value=[]):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    assert len(storage.read_hourly()) == 2
    obs = storage.read_observations()
    assert len(obs) == 1
    assert obs.iloc[0]["temp_max_c"] == 33.0  # máximo de las horas


def test_backfill_guarda_forecast_historico(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2024-06-10T14:00", "temp_c": 33.0, "humedad": 70.0, "nubosidad": 30.0}]
    fcst = [{"fecha": "2024-06-10", "forecast_max": 32.7}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico", return_value=fcst):
        backfill.correr(desde=date(2024, 6, 10), hasta=date(2024, 6, 10))
    f = storage.read_forecast()
    assert len(f) == 1
    assert f.iloc[0]["forecast_max"] == 32.7


def test_backfill_tolera_forecast_sin_cobertura(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2020-01-01T14:00", "temp_c": 33.0, "humedad": 70.0, "nubosidad": 30.0}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico",
               side_effect=RuntimeError("fuera de rango")):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    # El backfill horario no se cae aunque el forecast histórico falle.
    assert len(storage.read_hourly()) == 1
    assert len(storage.read_forecast()) == 0


def test_backfill_correr_sobreescribe_con_wunderground(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2020-01-01T14:00", "temp_c": 30.0, "humedad": 70.0, "nubosidad": 30.0}]
    wu = [{"fecha": "2020-01-01", "temp_max_c": 33.0}]  # medición real MPMG > ERA5
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico", return_value=[]), \
         patch("src.backfill.wunderground.fetch_via_api", return_value=wu):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    obs = storage.read_observations()
    # Wunderground (33.0) debe ganar sobre el pico derivado de Open-Meteo (30.0).
    assert obs[obs["fecha"] == "2020-01-01"].iloc[0]["temp_max_c"] == 33.0


def test_backfill_correr_sin_wunderground_usa_open_meteo(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2020-01-01T14:00", "temp_c": 30.0, "humedad": 70.0, "nubosidad": 30.0}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico", return_value=[]), \
         patch("src.backfill.wunderground.fetch_via_api", side_effect=RuntimeError("sin key")):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    obs = storage.read_observations()
    # Sin API de Wunderground, queda el pico de Open-Meteo; no falla.
    assert obs[obs["fecha"] == "2020-01-01"].iloc[0]["temp_max_c"] == 30.0


def test_actualizar_reciente_prefiere_wunderground(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2026-06-10T14:00", "temp_c": 33.0, "humedad": 70.0, "nubosidad": 30.0}]
    wu = [{"fecha": "2026-06-10", "temp_max_c": 32.4}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico", return_value=[]), \
         patch("src.backfill.wunderground.fetch_via_api", return_value=wu):
        backfill.actualizar_reciente(dias=7)
    obs = storage.read_observations()
    fila = obs[obs["fecha"] == "2026-06-10"].iloc[0]
    # Wunderground (verdad MPMG) gana sobre el derivado de Open-Meteo (33.0).
    assert fila["temp_max_c"] == 32.4


def test_actualizar_reciente_sin_wunderground_usa_open_meteo(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2026-06-10T14:00", "temp_c": 33.0, "humedad": 70.0, "nubosidad": 30.0}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.openmeteo.fetch_forecast_max_historico", return_value=[]), \
         patch("src.backfill.wunderground.fetch_via_api", side_effect=RuntimeError("sin key")):
        backfill.actualizar_reciente(dias=7)
    obs = storage.read_observations()
    fila = obs[obs["fecha"] == "2026-06-10"].iloc[0]
    assert fila["temp_max_c"] == 33.0  # cae al target de Open-Meteo, no se cuelga
