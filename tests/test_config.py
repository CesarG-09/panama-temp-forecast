from datetime import date
from src import config


def test_coordenadas_y_horas_de_decision():
    assert abs(config.LAT - 8.973) < 0.01
    assert abs(config.LON - (-79.556)) < 0.01
    assert config.HORAS_DECISION == list(range(6, 17))
    assert config.TZ == "America/Panama"
    assert config.FECHA_INICIO == date(2020, 1, 1)


def test_rutas_de_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    assert config.ruta_observaciones().name == "observations.csv"
    assert config.ruta_predicciones().name == "predictions.csv"
    assert config.ruta_evaluacion().name == "evaluation.csv"
    assert config.ruta_historico_horario().name == "hourly_history.csv"
    assert config.ruta_modelo().name == "peak_model.txt"
