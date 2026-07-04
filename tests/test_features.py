import pandas as pd
from src import features


def _intradia():
    # Horas 0..10 de un día, temperatura subiendo.
    return pd.DataFrame({
        "timestamp": [f"2026-06-16T{h:02d}:00" for h in range(11)],
        "temp_c": [24, 24, 23, 23, 24, 26, 28, 29, 30, 31, 31.5],
        "humedad": [88]*11,
        "nubosidad": [40]*11,
    })


def test_construir_fila_hasta_hora_h():
    fila = features.construir_fila(_intradia(), fecha="2026-06-16",
                                   hora_h=9, forecast_max=33.0)
    assert fila["hora_decision"] == 9
    assert fila["max_hasta_ahora"] == 31.0        # max de horas 0..9
    assert fila["temp_actual"] == 31.0            # hora 9
    assert fila["forecast_max"] == 33.0
    assert "doy_sin" in fila and "doy_cos" in fila
    assert fila["temp_lag1"] == 30.0              # hora 8
    assert round(fila["tasa_subida"], 2) == 1.0   # (31 - 30) por hora


def test_construir_fila_ignora_horas_posteriores_a_h():
    fila = features.construir_fila(_intradia(), fecha="2026-06-16",
                                   hora_h=6, forecast_max=None)
    assert fila["max_hasta_ahora"] == 28.0        # no ve las horas 7..10
    assert fila["forecast_max"] is None


def test_construir_fila_forecast_nullable():
    fila = features.construir_fila(_intradia(), fecha="2026-06-16",
                                   hora_h=10, forecast_max=None)
    assert fila["forecast_max"] is None


def test_features_mpmg_presentes():
    intradia = pd.DataFrame([
        {"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24.0 + h,
         "humedad": 80.0, "nubosidad": 30.0} for h in range(12)])
    mpmg = [{"hora": 8, "temp_c": 28.5}, {"hora": 9, "temp_c": 30.1},
            {"hora": 10, "temp_c": 31.4}, {"hora": 12, "temp_c": 33.0}]
    fila = features.construir_fila(intradia, fecha="2026-06-16", hora_h=10,
                                   forecast_max=32.0, mpmg_intradia=mpmg)
    # Solo cuenta lo observado hasta la hora de decisión (10): la hora 12 no.
    assert fila["temp_actual_mpmg"] == 31.4
    assert fila["max_hasta_ahora_mpmg"] == 31.4


def test_features_mpmg_usa_ultima_hora_disponible():
    intradia = pd.DataFrame([
        {"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24.0 + h,
         "humedad": 80.0, "nubosidad": 30.0} for h in range(12)])
    # La estación va atrasada: su última hora es 9 aunque decidimos a las 11.
    mpmg = [{"hora": 8, "temp_c": 31.0}, {"hora": 9, "temp_c": 29.5}]
    fila = features.construir_fila(intradia, fecha="2026-06-16", hora_h=11,
                                   forecast_max=32.0, mpmg_intradia=mpmg)
    assert fila["temp_actual_mpmg"] == 29.5      # última disponible <= 11
    assert fila["max_hasta_ahora_mpmg"] == 31.0  # máximo hasta las 11


def test_features_mpmg_none_sin_datos():
    intradia = pd.DataFrame([
        {"timestamp": "2026-06-16T08:00", "temp_c": 27.0,
         "humedad": 80.0, "nubosidad": 30.0}])
    fila = features.construir_fila(intradia, fecha="2026-06-16", hora_h=8,
                                   forecast_max=None)
    assert fila["temp_actual_mpmg"] is None
    assert fila["max_hasta_ahora_mpmg"] is None
    assert "temp_actual_mpmg" in features.FEATURE_COLS
    assert "max_hasta_ahora_mpmg" in features.FEATURE_COLS
