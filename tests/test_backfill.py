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
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    assert len(storage.read_hourly()) == 2
    obs = storage.read_observations()
    assert len(obs) == 1
    assert obs.iloc[0]["temp_max_c"] == 33.0  # máximo de las horas


def test_actualizar_reciente_prefiere_wunderground(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2026-06-10T14:00", "temp_c": 33.0, "humedad": 70.0, "nubosidad": 30.0}]
    wu = [{"fecha": "2026-06-10", "temp_max_c": 32.4}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
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
         patch("src.backfill.wunderground.fetch_via_api", side_effect=RuntimeError("sin key")):
        backfill.actualizar_reciente(dias=7)
    obs = storage.read_observations()
    fila = obs[obs["fecha"] == "2026-06-10"].iloc[0]
    assert fila["temp_max_c"] == 33.0  # cae al target de Open-Meteo, no se cuelga
