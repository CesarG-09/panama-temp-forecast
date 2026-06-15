import pandas as pd

from src import config

COLS = ["fecha_objetivo", "pred_c", "real_c", "error_c", "acierto"]


def evaluar(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
            umbral: float = config.UMBRAL_ACIERTO_C) -> pd.DataFrame:
    obs = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for fobj, grp in predicciones.groupby("fecha_objetivo"):
        if fobj not in obs:
            continue
        reciente = grp.sort_values("fecha_prediccion").iloc[-1]
        pred = float(reciente["temp_max_pred_c"])
        real = float(obs[fobj])
        error = round(pred - real, 1)
        filas.append({
            "fecha_objetivo": fobj, "pred_c": pred, "real_c": real,
            "error_c": error, "acierto": abs(error) <= umbral,
        })
    return pd.DataFrame(filas, columns=COLS).sort_values("fecha_objetivo").reset_index(drop=True)


def metricas(evaluacion: pd.DataFrame) -> dict:
    if len(evaluacion) == 0:
        return {"n": 0, "mae": None, "aciertos_pct": None}
    return {
        "n": int(len(evaluacion)),
        "mae": round(float(evaluacion["error_c"].abs().mean()), 2),
        "aciertos_pct": round(100 * float(evaluacion["acierto"].mean()), 1),
    }
