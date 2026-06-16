import pandas as pd

from src import config, features


def construir_set(hist_horario: pd.DataFrame, observaciones: pd.DataFrame) -> pd.DataFrame:
    """Ensambla la tabla de entrenamiento: una fila por (día observado × hora de decisión).

    El forecast histórico no está disponible en backfill, así que `forecast_max` = None
    (LightGBM lo trata como faltante). El target es el pico real (Wunderground).
    """
    obs = observaciones.dropna(subset=["temp_max_c"]).copy()
    target_por_fecha = dict(zip(obs["fecha"], obs["temp_max_c"]))

    df = hist_horario.copy()
    df["_fecha"] = df["timestamp"].str.slice(0, 10)

    filas = []
    for fecha, intradia in df.groupby("_fecha"):
        if fecha not in target_por_fecha:
            continue
        for h in config.HORAS_DECISION:
            fila = features.construir_fila(intradia, fecha=fecha, hora_h=h,
                                           forecast_max=None)
            if fila["max_hasta_ahora"] is None:
                continue
            fila["target"] = float(target_por_fecha[fecha])
            filas.append(fila)
    return pd.DataFrame(filas)
