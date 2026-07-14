import os
from datetime import date
from pathlib import Path

# Estación de referencia (la "verdad" del pico) y ubicación para Open-Meteo.
ESTACION = "MPMG:9:PA"
LAT = 8.973
LON = -79.556
TZ = "America/Panama"

HORAS_DECISION = list(range(6, 17))  # 6am..4pm local: franja en que corre el pipeline
# La predicción oficial se congela antes de esta hora: el pico efectivo del día
# ocurre entre las 12 y las 2 pm, y una predicción emitida a partir de las 12
# ya no anticipa nada (el piso MPMG la vuelve el máximo observado).
HORA_CORTE = 12
UMBRAL_ACIERTO_C = 1.5
FECHA_INICIO = date(2020, 1, 1)
MODELO_VERSION = "gbm-q-v2"

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def data_dir() -> Path:
    return Path(os.environ.get("PTF_DATA_DIR", _DEFAULT_DATA_DIR))


def model_dir() -> Path:
    return Path(os.environ.get("PTF_MODEL_DIR", _DEFAULT_MODEL_DIR))


def ruta_observaciones() -> Path:
    return data_dir() / "observations.csv"


def ruta_predicciones() -> Path:
    return data_dir() / "predictions.csv"


def ruta_evaluacion() -> Path:
    return data_dir() / "evaluation.csv"


def ruta_historico_horario() -> Path:
    return data_dir() / "hourly_history.csv"


def ruta_forecast() -> Path:
    return data_dir() / "forecast_history.csv"


def ruta_modelo() -> Path:
    return model_dir() / "peak_model.txt"


def ruta_peak_hours() -> Path:
    return data_dir() / "peak_hours.csv"


def ruta_mpmg_horario() -> Path:
    return data_dir() / "mpmg_hourly.csv"
