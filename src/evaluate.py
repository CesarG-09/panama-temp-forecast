import pandas as pd


def evaluar(predicciones: pd.DataFrame, observaciones: pd.DataFrame) -> pd.DataFrame:
    """Compara cada predicción horaria contra el pico real del día.

    Devuelve filas: fecha_objetivo, hora_decision, pico_pred, pico_real, error_c.
    Solo incluye días con observación (pico real) ya disponible.
    """
    if len(predicciones) == 0 or len(observaciones) == 0:
        return pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                     "pico_pred", "pico_real", "error_c"])
    real = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for _, p in predicciones.iterrows():
        f = p["fecha_objetivo"]
        if f not in real:
            continue
        pr = float(real[f])
        filas.append({
            "fecha_objetivo": f,
            "hora_decision": int(p["hora_decision"]),
            "pico_pred": float(p["pico_pred"]),
            "pico_real": pr,
            "error_c": round(float(p["pico_pred"]) - pr, 2),
        })
    return pd.DataFrame(filas)
