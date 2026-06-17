import pandas as pd

from src import config

_PRED_COLS = ["run_timestamp", "fecha_objetivo", "hora_decision", "pico_pred",
              "p10", "p90", "modelo_version"]
_EVAL_COLS = ["fecha_objetivo", "hora_decision", "pico_pred", "pico_real", "error_c"]
_HOURLY_COLS = ["timestamp", "temp_c", "humedad", "nubosidad"]
_OBS_COLS = ["fecha", "temp_max_c"]
_FORECAST_COLS = ["fecha", "forecast_max"]


def _read_csv(ruta, cols) -> pd.DataFrame:
    if ruta.exists():
        return pd.read_csv(ruta)
    return pd.DataFrame(columns=cols)


def read_observations() -> pd.DataFrame:
    return _read_csv(config.ruta_observaciones(), _OBS_COLS)


def upsert_observations(filas: list[dict]) -> None:
    ruta = config.ruta_observaciones()
    df = pd.concat([read_observations(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates("fecha", keep="last").sort_values("fecha")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_hourly() -> pd.DataFrame:
    return _read_csv(config.ruta_historico_horario(), _HOURLY_COLS)


def upsert_hourly(filas: list[dict]) -> None:
    ruta = config.ruta_historico_horario()
    df = pd.concat([read_hourly(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_forecast() -> pd.DataFrame:
    return _read_csv(config.ruta_forecast(), _FORECAST_COLS)


def upsert_forecast(filas: list[dict]) -> None:
    ruta = config.ruta_forecast()
    df = pd.concat([read_forecast(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates("fecha", keep="last").sort_values("fecha")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_predictions() -> pd.DataFrame:
    return _read_csv(config.ruta_predicciones(), _PRED_COLS)


def append_prediction(fila: dict) -> None:
    ruta = config.ruta_predicciones()
    df = pd.concat([read_predictions(), pd.DataFrame([fila])], ignore_index=True)
    # Upsert por (fecha_objetivo, hora_decision): una re-corrida en la misma
    # hora reemplaza la predicción previa en vez de duplicar el punto.
    df = df.drop_duplicates(["fecha_objetivo", "hora_decision"], keep="last") \
        .sort_values(["fecha_objetivo", "hora_decision"])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_evaluation() -> pd.DataFrame:
    return _read_csv(config.ruta_evaluacion(), _EVAL_COLS)


def write_evaluation(df: pd.DataFrame) -> None:
    ruta = config.ruta_evaluacion()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
