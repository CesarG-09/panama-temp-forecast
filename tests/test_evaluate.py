import pandas as pd

from src import evaluate


def _predicciones():
    return pd.DataFrame({
        "fecha_prediccion": ["2021-05-30", "2021-05-31", "2021-05-30"],
        "fecha_objetivo": ["2021-06-01", "2021-06-01", "2021-06-02"],
        "temp_max_pred_c": [31.0, 30.5, 35.0],
        "modelo_version": ["clima-v1"] * 3,
    })


def _observaciones():
    return pd.DataFrame({"fecha": ["2021-06-01"], "temp_max_c": [30.0]})


def test_evaluar_usa_la_prediccion_mas_reciente_por_objetivo():
    ev = evaluate.evaluar(_predicciones(), _observaciones(), umbral=1.5)
    # Sólo 2021-06-01 tiene observación; gana la predicción del 2021-05-31 (30.5)
    assert len(ev) == 1
    fila = ev.iloc[0]
    assert fila["fecha_objetivo"] == "2021-06-01"
    assert fila["pred_c"] == 30.5
    assert fila["real_c"] == 30.0
    assert fila["error_c"] == 0.5
    assert bool(fila["acierto"]) is True


def test_evaluar_marca_fallo_fuera_de_umbral():
    preds = pd.DataFrame({
        "fecha_prediccion": ["2021-05-31"], "fecha_objetivo": ["2021-06-01"],
        "temp_max_pred_c": [33.0], "modelo_version": ["clima-v1"],
    })
    ev = evaluate.evaluar(preds, _observaciones(), umbral=1.5)
    assert bool(ev.iloc[0]["acierto"]) is False


def test_metricas_agrega_mae_y_aciertos():
    ev = pd.DataFrame({
        "fecha_objetivo": ["a", "b", "c", "d"],
        "pred_c": [0, 0, 0, 0], "real_c": [0, 0, 0, 0],
        "error_c": [1.0, -1.0, 2.0, -2.0],
        "acierto": [True, True, False, False],
    })
    m = evaluate.metricas(ev)
    assert m["n"] == 4
    assert m["mae"] == 1.5
    assert m["aciertos_pct"] == 50.0


def test_metricas_vacio():
    m = evaluate.metricas(pd.DataFrame(columns=["error_c", "acierto"]))
    assert m == {"n": 0, "mae": None, "aciertos_pct": None}
