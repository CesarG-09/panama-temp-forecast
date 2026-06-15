import os
from datetime import date
from pathlib import Path

ESTACION = "MPMG:9:PA"
TZ = "America/Panama"
HORIZONTE_DIAS = 7
UMBRAL_ACIERTO_C = 1.5
FECHA_INICIO = date(2020, 1, 1)
MODELO_VERSION = "clima-v1"

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def data_dir() -> Path:
    return Path(os.environ.get("PTF_DATA_DIR", _DEFAULT_DATA_DIR))


def ruta_observaciones() -> Path:
    return data_dir() / "observations.csv"


def ruta_predicciones() -> Path:
    return data_dir() / "predictions.csv"


def ruta_evaluacion() -> Path:
    return data_dir() / "evaluation.csv"
