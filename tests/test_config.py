from datetime import date
from pathlib import Path
from src import config


def test_constantes_basicas():
    assert config.ESTACION == "MPMG:9:PA"
    assert config.TZ == "America/Panama"
    assert config.HORIZONTE_DIAS == 7
    assert config.UMBRAL_ACIERTO_C == 1.5
    assert config.FECHA_INICIO == date(2020, 1, 1)


def test_data_dir_respeta_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    assert config.data_dir() == tmp_path
    assert config.ruta_observaciones() == tmp_path / "observations.csv"
