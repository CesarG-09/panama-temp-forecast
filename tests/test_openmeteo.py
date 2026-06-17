from datetime import date
from unittest.mock import patch

from src.sources import openmeteo


def test_parse_archivo_horario_a_filas():
    payload = {
        "hourly": {
            "time": ["2020-01-01T00:00", "2020-01-01T01:00", "2020-01-01T02:00"],
            "temperature_2m": [24.0, 23.5, 23.0],
            "relative_humidity_2m": [80, 82, 85],
            "cloud_cover": [10, 20, 30],
        }
    }
    filas = openmeteo.parse_horario(payload)
    assert filas[0] == {
        "timestamp": "2020-01-01T00:00",
        "temp_c": 24.0,
        "humedad": 80.0,
        "nubosidad": 10.0,
    }
    assert len(filas) == 3


def test_parse_horario_omite_nulos():
    payload = {
        "hourly": {
            "time": ["2020-01-01T00:00", "2020-01-01T01:00"],
            "temperature_2m": [None, 23.5],
            "relative_humidity_2m": [80, 82],
            "cloud_cover": [10, 20],
        }
    }
    filas = openmeteo.parse_horario(payload)
    assert len(filas) == 1
    assert filas[0]["timestamp"] == "2020-01-01T01:00"


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_fetch_archivo_arma_params_y_parsea():
    data = {"hourly": {"time": ["2020-01-01T00:00"], "temperature_2m": [24.0],
                       "relative_humidity_2m": [80], "cloud_cover": [10]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)) as g:
        filas = openmeteo.fetch_archivo(date(2020, 1, 1), date(2020, 1, 2))
    assert filas[0]["temp_c"] == 24.0
    _, kwargs = g.call_args
    assert kwargs["params"]["start_date"] == "2020-01-01"
    assert kwargs["params"]["end_date"] == "2020-01-02"
    assert kwargs["params"]["timezone"] == "America/Panama"


def test_parse_forecast_max_diario_omite_nulos():
    payload = {"daily": {"time": ["2024-06-01", "2024-06-02"],
                         "temperature_2m_max": [33.1, None]}}
    filas = openmeteo.parse_forecast_max_diario(payload)
    assert filas == [{"fecha": "2024-06-01", "forecast_max": 33.1}]


def test_fetch_forecast_max_historico_arma_params_y_parsea():
    data = {"daily": {"time": ["2024-06-01"], "temperature_2m_max": [33.1]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)) as g:
        filas = openmeteo.fetch_forecast_max_historico(date(2024, 6, 1), date(2024, 6, 1))
    assert filas == [{"fecha": "2024-06-01", "forecast_max": 33.1}]
    args, kwargs = g.call_args
    assert args[0] == openmeteo.HIST_FORECAST_URL
    assert kwargs["params"]["daily"] == "temperature_2m_max"


def test_fetch_forecast_maxima_de_hoy():
    data = {"daily": {"time": ["2026-06-16"], "temperature_2m_max": [33.4]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)):
        val = openmeteo.fetch_forecast_max(date(2026, 6, 16))
    assert val == 33.4


def test_fetch_intradia_usa_past_days():
    data = {"hourly": {"time": ["2026-06-16T00:00"], "temperature_2m": [26.0],
                       "relative_humidity_2m": [88], "cloud_cover": [40]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)) as g:
        filas = openmeteo.fetch_intradia(date(2026, 6, 16))
    assert filas[0]["temp_c"] == 26.0
    _, kwargs = g.call_args
    assert kwargs["params"]["past_days"] >= 1
