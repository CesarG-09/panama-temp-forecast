from datetime import date
from unittest.mock import patch
from src import backfill, storage


def test_backfill_carga_horario_y_observaciones(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2020-01-01T10:00", "temp_c": 30.0,
              "humedad": 80.0, "nubosidad": 20.0}]
    obs = [{"fecha": "2020-01-01", "temp_max_c": 31.0}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.wunderground.obtener_observaciones", return_value=obs):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    assert len(storage.read_hourly()) == 1
    assert len(storage.read_observations()) == 1
