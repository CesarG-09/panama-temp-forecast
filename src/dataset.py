import pandas as pd

from src import config, features


def construir_set(hist_horario: pd.DataFrame, observaciones: pd.DataFrame,
                  forecast_por_fecha: dict | None = None,
                  mpmg_horario: pd.DataFrame | None = None) -> pd.DataFrame:
    """Ensambla la tabla de entrenamiento: una fila por (día observado × hora de decisión).

    `forecast_por_fecha` mapea fecha -> pronóstico de máxima del día (forecast_max).
    `mpmg_horario` es el horario real de la estación (fecha, hora, temp_c) para las
    features MPMG. Lo que falte queda None (LightGBM lo trata como faltante). El
    target es el pico real (Wunderground / Open-Meteo).
    """
    forecast_por_fecha = forecast_por_fecha or {}
    mpmg_por_fecha: dict[str, list[dict]] = {}
    if mpmg_horario is not None and len(mpmg_horario):
        for f, g in mpmg_horario.groupby("fecha"):
            mpmg_por_fecha[str(f)] = [
                {"hora": int(r["hora"]), "temp_c": float(r["temp_c"])}
                for _, r in g.iterrows()]
    obs = observaciones.dropna(subset=["temp_max_c"]).copy()
    target_por_fecha = dict(zip(obs["fecha"], obs["temp_max_c"]))

    df = hist_horario.copy()
    df["_fecha"] = df["timestamp"].str.slice(0, 10)

    filas = []
    for fecha, intradia in df.groupby("_fecha"):
        if fecha not in target_por_fecha:
            continue
        fcst = forecast_por_fecha.get(fecha)
        for h in config.HORAS_DECISION:
            fila = features.construir_fila(intradia, fecha=fecha, hora_h=h,
                                           forecast_max=fcst,
                                           mpmg_intradia=mpmg_por_fecha.get(fecha))
            if fila["max_hasta_ahora"] is None:
                continue
            fila["target"] = float(target_por_fecha[fecha])
            filas.append(fila)
    return pd.DataFrame(filas)
