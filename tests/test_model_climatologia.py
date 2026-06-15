import pandas as pd

from src.model import Climatologia


def _hist_constante(valor, dias=400):
    fechas = pd.date_range("2020-01-01", periods=dias, freq="D")
    return pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"),
                         "temp_max_c": [valor] * dias})


def test_climatologia_predice_la_media_del_dia_del_anio():
    hist = _hist_constante(30.0)
    modelo = Climatologia().ajustar(hist)
    assert modelo.predecir(["2021-06-01"])[0] == 30.0


def test_climatologia_captura_estacionalidad():
    # Enero frío (28), julio caluroso (34)
    fechas = pd.date_range("2020-01-01", periods=730, freq="D")
    temps = [28.0 if f.month in (12, 1, 2) else 34.0 for f in fechas]
    hist = pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"), "temp_max_c": temps})
    modelo = Climatologia(ventana_dias=7).ajustar(hist)
    enero = modelo.predecir(["2021-01-15"])[0]
    julio = modelo.predecir(["2021-07-15"])[0]
    assert enero < 30.0
    assert julio > 32.0
