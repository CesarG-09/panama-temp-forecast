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
