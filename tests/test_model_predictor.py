import pandas as pd

from src.model import Predictor


def _hist_constante(valor, dias=400):
    fechas = pd.date_range("2020-01-01", periods=dias, freq="D")
    return pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"),
                         "temp_max_c": [valor] * dias})


def test_predictor_sin_anomalia_ni_sesgo_es_climatologia():
    hist = _hist_constante(30.0)
    pred = Predictor().ajustar(hist)
    assert pred.predecir(["2021-06-01"]) == [30.0]


def test_anomalia_reciente_desplaza_la_prediccion():
    hist = _hist_constante(30.0, dias=400)
    hist.loc[hist.index[-3:], "temp_max_c"] = 33.0  # últimos 3 días más calientes
    pred = Predictor(dias_anomalia=3).ajustar(hist)
    assert pred.predecir(["2021-06-01"])[0] > 30.0


def test_anomalia_decae_en_el_horizonte():
    # Con una anomalía cálida reciente, el día más cercano debe conservar más
    # anomalía que los lejanos, que revierten hacia la climatología (30.0).
    hist = _hist_constante(30.0, dias=400)
    hist.loc[hist.index[-3:], "temp_max_c"] = 33.0
    pred = Predictor(dias_anomalia=3).ajustar(hist)
    fechas = [f"2021-06-0{i}" for i in range(1, 8)]  # 7 días consecutivos
    valores = pred.predecir(fechas)
    assert valores[0] > valores[-1]          # decae con el horizonte
    assert valores[0] > 32.0                 # el cercano conserva la anomalía (~+3)
    assert valores[-1] < valores[0]          # el lejano vuelve hacia ~30
    assert all(a >= b for a, b in zip(valores, valores[1:]))  # monótono no creciente


def test_correccion_de_sesgo_reduce_sobreprediccion():
    hist = _hist_constante(30.0)
    # El modelo venía prediciendo 2 °C de más (error_c = pred - real = +2)
    evaluacion = pd.DataFrame({
        "fecha_objetivo": ["2021-05-29", "2021-05-30", "2021-05-31"],
        "pred_c": [32.0, 32.0, 32.0],
        "real_c": [30.0, 30.0, 30.0],
        "error_c": [2.0, 2.0, 2.0],
        "acierto": [False, False, False],
    })
    pred = Predictor().ajustar(hist, evaluacion)
    # Se corrige hacia abajo ~2 °C respecto a la climatología (30.0)
    assert pred.predecir(["2021-06-01"])[0] == 28.0
