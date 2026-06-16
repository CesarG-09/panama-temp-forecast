import math

import pandas as pd

# Orden canónico de columnas de features (lo consume dataset/model/predict).
FEATURE_COLS = [
    "hora_decision", "doy_sin", "doy_cos", "mes",
    "max_hasta_ahora", "temp_actual", "temp_lag1", "temp_lag2", "temp_lag3",
    "tasa_subida", "humedad_actual", "nubosidad_actual", "forecast_max",
]


def _hora(ts: str) -> int:
    return int(ts[11:13])


def construir_fila(intradia: pd.DataFrame, fecha: str, hora_h: int,
                   forecast_max: float | None) -> dict:
    """Construye una fila de features usando solo horas <= hora_h del día `fecha`."""
    df = intradia.copy()
    df = df[df["timestamp"].str.startswith(fecha)]
    df = df.assign(_h=df["timestamp"].map(_hora)).sort_values("_h")
    hasta = df[df["_h"] <= hora_h]

    fecha_ts = pd.Timestamp(fecha)
    doy = fecha_ts.dayofyear

    def _temp_en(h: int):
        sel = hasta[hasta["_h"] == h]["temp_c"]
        return float(sel.iloc[0]) if len(sel) else None

    temp_actual = _temp_en(hora_h)
    temp_lag1 = _temp_en(hora_h - 1)
    temp_lag2 = _temp_en(hora_h - 2)
    temp_lag3 = _temp_en(hora_h - 3)
    tasa = (temp_actual - temp_lag1) if (temp_actual is not None
                                         and temp_lag1 is not None) else None

    def _ultimo(col: str):
        sel = hasta[col].dropna()
        return float(sel.iloc[-1]) if len(sel) else None

    return {
        "fecha_objetivo": fecha,
        "hora_decision": hora_h,
        "doy_sin": math.sin(2 * math.pi * doy / 365.25),
        "doy_cos": math.cos(2 * math.pi * doy / 365.25),
        "mes": fecha_ts.month,
        "max_hasta_ahora": float(hasta["temp_c"].max()) if len(hasta) else None,
        "temp_actual": temp_actual,
        "temp_lag1": temp_lag1,
        "temp_lag2": temp_lag2,
        "temp_lag3": temp_lag3,
        "tasa_subida": tasa,
        "humedad_actual": _ultimo("humedad"),
        "nubosidad_actual": _ultimo("nubosidad"),
        "forecast_max": forecast_max,
    }
