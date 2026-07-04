import pandas as pd
from src import dataset, config


def _hist_horario():
    filas = []
    for dia in ("2026-06-14", "2026-06-15"):
        for h in range(17):
            filas.append({"timestamp": f"{dia}T{h:02d}:00",
                          "temp_c": 24 + h * 0.5,
                          "humedad": 80.0, "nubosidad": 30.0})
    return pd.DataFrame(filas)


def _observaciones():
    return pd.DataFrame([
        {"fecha": "2026-06-14", "temp_max_c": 32.0},
        {"fecha": "2026-06-15", "temp_max_c": 33.0},
    ])


def test_construir_set_genera_una_fila_por_dia_y_hora():
    df = dataset.construir_set(_hist_horario(), _observaciones())
    # 2 días * len(HORAS_DECISION) filas
    assert len(df) == 2 * len(config.HORAS_DECISION)
    assert "target" in df.columns
    # El target es el pico real del día correspondiente.
    fila_14 = df[df["fecha_objetivo"] == "2026-06-14"].iloc[0]
    assert fila_14["target"] == 32.0


def test_construir_set_omite_dias_sin_observacion():
    obs = _observaciones().iloc[:1]  # solo 2026-06-14
    df = dataset.construir_set(_hist_horario(), obs)
    assert set(df["fecha_objetivo"].unique()) == {"2026-06-14"}


def test_construir_set_usa_forecast_por_fecha():
    fpf = {"2026-06-14": 31.5, "2026-06-15": 33.2}
    df = dataset.construir_set(_hist_horario(), _observaciones(), fpf)
    fila_14 = df[df["fecha_objetivo"] == "2026-06-14"].iloc[0]
    assert fila_14["forecast_max"] == 31.5
    fila_15 = df[df["fecha_objetivo"] == "2026-06-15"].iloc[0]
    assert fila_15["forecast_max"] == 33.2


def test_construir_set_incluye_features_mpmg():
    hist = pd.DataFrame([
        {"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24.0 + h,
         "humedad": 80.0, "nubosidad": 30.0} for h in range(17)])
    obs = pd.DataFrame([{"fecha": "2026-06-16", "temp_max_c": 33.5}])
    mpmg = pd.DataFrame([{"fecha": "2026-06-16", "hora": 9, "temp_c": 30.2},
                         {"fecha": "2026-06-16", "hora": 10, "temp_c": 31.8}])
    set_ent = dataset.construir_set(hist, obs, {}, mpmg_horario=mpmg)
    fila_10 = set_ent[set_ent["hora_decision"] == 10].iloc[0]
    assert fila_10["max_hasta_ahora_mpmg"] == 31.8
    fila_6 = set_ent[set_ent["hora_decision"] == 6].iloc[0]
    assert pd.isna(fila_6["max_hasta_ahora_mpmg"]) or \
        fila_6["max_hasta_ahora_mpmg"] is None
