from pathlib import Path

import pandas as pd

from src import config


def read_csv(ruta: Path, columnas: list[str]) -> pd.DataFrame:
    if Path(ruta).exists():
        return pd.read_csv(ruta, dtype={"fecha": str, "fecha_objetivo": str,
                                        "fecha_prediccion": str})
    return pd.DataFrame(columns=columnas)


def upsert_rows(ruta: Path, filas: list[dict], columnas: list[str],
                claves: list[str]) -> pd.DataFrame:
    ruta = Path(ruta)
    nuevo = pd.DataFrame(filas, columns=columnas)
    if ruta.exists():
        df = pd.concat([read_csv(ruta, columnas), nuevo], ignore_index=True)
    else:
        df = nuevo
    df = (df.drop_duplicates(subset=claves, keep="last")
            .sort_values(claves)
            .reset_index(drop=True))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
    return df


OBS_COLS = ["fecha", "temp_max_c"]
PRED_COLS = ["fecha_prediccion", "fecha_objetivo", "temp_max_pred_c", "modelo_version"]
EVAL_COLS = ["fecha_objetivo", "pred_c", "real_c", "error_c", "acierto"]


def read_observations() -> pd.DataFrame:
    return read_csv(config.ruta_observaciones(), OBS_COLS)


def upsert_observations(filas: list[dict]) -> pd.DataFrame:
    return upsert_rows(config.ruta_observaciones(), filas, OBS_COLS, ["fecha"])


def read_predictions() -> pd.DataFrame:
    return read_csv(config.ruta_predicciones(), PRED_COLS)


def upsert_predictions(filas: list[dict]) -> pd.DataFrame:
    return upsert_rows(config.ruta_predicciones(), filas, PRED_COLS,
                       ["fecha_prediccion", "fecha_objetivo"])


def write_evaluation(df: pd.DataFrame) -> None:
    ruta = config.ruta_evaluacion()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_evaluation() -> pd.DataFrame:
    return read_csv(config.ruta_evaluacion(), EVAL_COLS)
