import json
import pandas as pd
from src import export


def test_construir_payload_estructura():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31.5, "p90": 34.5,
         "modelo_version": "gbm-q-v1"},
        {"run_timestamp": "2026-06-16T17:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 12, "pico_pred": 32.8, "p10": 32.2, "p90": 33.4,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-15", "temp_max_c": 32.4}])
    evaluacion = pd.DataFrame([{"fecha_objetivo": "2026-06-15", "hora_decision": 12,
                               "pico_pred": 32.5, "pico_real": 32.4, "error_c": 0.1}])
    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy="2026-06-16")
    assert payload["hoy"] == "2026-06-16"
    # La predicción más reciente de hoy manda el número grande.
    assert payload["pico_hoy"]["pico_pred"] == 32.8
    assert payload["pico_hoy"]["p10"] == 32.2
    assert payload["pico_hoy"]["p90"] == 33.4
    assert len(payload["convergencia_hoy"]) == 2
    assert payload["curva_hoy"] == []  # sin curva por defecto
    assert payload["temp_actual"] is None  # sin temperatura actual por defecto
    assert "error_por_hora" in payload
    assert "pasadas_vs_real" in payload
    assert "evolucion_modelo" in payload
    assert "observados_recientes" not in payload


def test_construir_payload_incluye_sello_de_generado():
    vacio_pred = pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                       "pico_pred", "p10", "p90"])
    vacio_obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    vacio_eval = pd.DataFrame(columns=["hora_decision", "error_c"])

    # Explícito: se respeta lo que se pasa.
    payload = export.construir_payload(vacio_pred, vacio_obs, vacio_eval,
                                       hoy="2026-06-16",
                                       generado="2026-06-16T14:23-05:00")
    assert payload["generado"] == "2026-06-16T14:23-05:00"

    # Por defecto: se rellena con un sello no vacío (hora de Panamá).
    payload2 = export.construir_payload(vacio_pred, vacio_obs, vacio_eval,
                                        hoy="2026-06-16")
    assert isinstance(payload2["generado"], str) and payload2["generado"]


def test_construir_payload_incluye_curva():
    curva = [{"hora": 6, "temp_c": 25.0}, {"hora": 7, "temp_c": 26.1}]
    payload = export.construir_payload(pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                                            "pico_pred", "p10", "p90"]),
                                       pd.DataFrame(columns=["fecha", "temp_max_c"]),
                                       pd.DataFrame(columns=["hora_decision", "error_c"]),
                                       hoy="2026-06-16", curva_hoy=curva)
    assert payload["curva_hoy"] == curva


def test_construir_payload_incluye_temp_actual():
    actual = {"temp_c": 31.2, "hora_local": "13:40"}
    payload = export.construir_payload(pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                                            "pico_pred", "p10", "p90"]),
                                       pd.DataFrame(columns=["fecha", "temp_max_c"]),
                                       pd.DataFrame(columns=["hora_decision", "error_c"]),
                                       hoy="2026-06-16", temp_actual=actual)
    assert payload["temp_actual"] == actual


def test_exportar_escribe_json(tmp_path):
    payload = {"hoy": "2026-06-16", "pico_hoy": None,
               "convergencia_hoy": [], "error_por_hora": []}
    ruta = tmp_path / "data.json"
    export.exportar(ruta, payload)
    assert json.loads(ruta.read_text())["hoy"] == "2026-06-16"


def test_pasadas_vs_real_manana_y_final():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 6,
         "pico_pred": 30.8, "p10": 29.5, "p90": 32.5, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 16,
         "pico_pred": 31.6, "p10": 29.8, "p90": 33.0, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-20", "temp_max_c": 33.0}])
    out = export.construir_pasadas_vs_real(predicciones, observaciones)
    assert out == [{
        "fecha": "2026-06-20", "real": 33.0,
        "manana_p50": 30.8, "manana_p10": 29.5, "manana_p90": 32.5,
        "final_p50": 31.6,
    }]


def test_pasadas_vs_real_excluye_dias_sin_pico_real():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-21", "hora_decision": 6,
         "pico_pred": 30.0, "p10": 29.0, "p90": 31.0, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame(columns=["fecha", "temp_max_c"])
    assert export.construir_pasadas_vs_real(predicciones, observaciones) == []


def test_pasadas_vs_real_un_solo_punto_manana_igual_final():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 9,
         "pico_pred": 31.4, "p10": 30.4, "p90": 32.6, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-22", "temp_max_c": 30.0}])
    out = export.construir_pasadas_vs_real(predicciones, observaciones)
    assert out[0]["manana_p50"] == 31.4 and out[0]["final_p50"] == 31.4


def test_evolucion_error_y_rolling():
    evaluacion = pd.DataFrame([
        {"fecha_objetivo": "2026-06-01", "hora_decision": 6,  "pico_pred": 0, "pico_real": 0, "error_c": 2.0},
        {"fecha_objetivo": "2026-06-01", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": -0.5},
        {"fecha_objetivo": "2026-06-02", "hora_decision": 6,  "pico_pred": 0, "pico_real": 0, "error_c": -1.0},
        {"fecha_objetivo": "2026-06-02", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": 0.2},
    ])
    out = export.construir_evolucion(evaluacion, ventana=7, umbral=1.5)
    assert out[0] == {"fecha": "2026-06-01", "err_manana": 2.0, "err_final": 0.5,
                      "mae7_manana": 2.0, "mae7_final": 0.5,
                      "acierto7_manana": 0.0, "acierto7_final": 1.0}
    assert out[1] == {"fecha": "2026-06-02", "err_manana": 1.0, "err_final": 0.2,
                      "mae7_manana": 1.5, "mae7_final": 0.35,
                      "acierto7_manana": 0.5, "acierto7_final": 1.0}


def test_evolucion_vacia():
    vacio = pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                  "pico_pred", "pico_real", "error_c"])
    assert export.construir_evolucion(vacio) == []


def test_pico_hoy_incluye_prob_acierto():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-16", "hora_decision": 16,
         "pico_pred": 33.0, "p10": 32.0, "p90": 34.0, "modelo_version": "v"},
    ])
    # A la hora 16: 3 días; acierto = trunc(pred) == real. 2 de 3 -> 67%
    evaluacion = pd.DataFrame([
        {"fecha_objetivo": "2026-06-13", "hora_decision": 16, "pico_pred": 32.4, "pico_real": 32.0, "error_c": 0.4},
        {"fecha_objetivo": "2026-06-14", "hora_decision": 16, "pico_pred": 31.0, "pico_real": 32.0, "error_c": -1.0},
        {"fecha_objetivo": "2026-06-15", "hora_decision": 16, "pico_pred": 33.9, "pico_real": 33.0, "error_c": 0.9},
    ])
    obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    payload = export.construir_payload(predicciones, obs, evaluacion, hoy="2026-06-16")
    assert payload["pico_hoy"]["prob_acierto"] == 67
    assert payload["pico_hoy"]["prob_n"] == 3


def test_pico_hoy_prob_acierto_null_sin_historial():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-16", "hora_decision": 7,
         "pico_pred": 33.0, "p10": 32.0, "p90": 34.0, "modelo_version": "v"},
    ])
    evaluacion = pd.DataFrame([
        {"fecha_objetivo": "2026-06-13", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": 0.5},
    ])
    obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    payload = export.construir_payload(predicciones, obs, evaluacion, hoy="2026-06-16")
    assert payload["pico_hoy"]["prob_acierto"] is None
    assert payload["pico_hoy"]["prob_n"] is None


def test_tabla_historica_columnas_y_orden():
    # 2026-06-20: predijo 31 (truncado) desde la hora 6; pico real a las 14 -> antes.
    # 2026-06-21: predijo 33 solo en la final (16); pico a las 13 -> NO antes.
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 6,  "pico_pred": 31.2, "p10": 30, "p90": 33, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 16, "pico_pred": 31.6, "p10": 30, "p90": 33, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-21", "hora_decision": 16, "pico_pred": 33.2, "p10": 32, "p90": 34, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([
        {"fecha": "2026-06-20", "temp_max_c": 33.0},
        {"fecha": "2026-06-21", "temp_max_c": 33.0},
    ])
    horas_pico = {"2026-06-20": 14, "2026-06-21": 13}
    out = export.construir_tabla_historica(predicciones, observaciones, horas_pico)
    assert [r["fecha"] for r in out] == ["2026-06-21", "2026-06-20"]
    assert out[0] == {"fecha": "2026-06-21", "prediccion": 33, "real": 33,
                      "hora_prediccion": 16, "hora_pico": 13, "antes": False,
                      "se_cumplio": True, "tasa_error_pct": 0.0, "diferencia": 0}
    assert out[1] == {"fecha": "2026-06-20", "prediccion": 31, "real": 33,
                      "hora_prediccion": 6, "hora_pico": 14, "antes": True,
                      "se_cumplio": False, "tasa_error_pct": 6.1, "diferencia": -2}


def test_tabla_historica_trunca_no_redondea():
    # 32.9 se TRUNCA a 32 (no 33). Sin horas_pico -> hora_pico/antes = None.
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-19", "hora_decision": 16,
         "pico_pred": 32.9, "p10": 32, "p90": 33, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-19", "temp_max_c": 33.0}])
    out = export.construir_tabla_historica(predicciones, observaciones)
    assert out[0] == {"fecha": "2026-06-19", "prediccion": 32, "real": 33,
                      "hora_prediccion": 16, "hora_pico": None, "antes": None,
                      "se_cumplio": False, "tasa_error_pct": 3.0, "diferencia": -1}


def test_tabla_historica_hora_prediccion_primera_coincidencia():
    # Predijo 31 a la hora 6, bajó a 30 a la 10, volvió a 31 en la final (16).
    # hora_prediccion = 6 (primera vez que el truncado fue el final).
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 6,  "pico_pred": 31.0, "p10": 30, "p90": 32, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 10, "pico_pred": 30.0, "p10": 29, "p90": 31, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 16, "pico_pred": 31.0, "p10": 30, "p90": 32, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-22", "temp_max_c": 31.0}])
    out = export.construir_tabla_historica(predicciones, observaciones)
    assert out[0]["hora_prediccion"] == 6
    assert out[0]["se_cumplio"] is True


def test_tabla_historica_tope_20():
    preds, obs = [], []
    for i in range(1, 26):
        f = f"2026-05-{i:02d}"
        preds.append({"run_timestamp": "x", "fecha_objetivo": f, "hora_decision": 16,
                      "pico_pred": 30.0, "p10": 29, "p90": 31, "modelo_version": "v"})
        obs.append({"fecha": f, "temp_max_c": 30.0})
    out = export.construir_tabla_historica(pd.DataFrame(preds), pd.DataFrame(obs))
    assert len(out) == 20
    assert out[0]["fecha"] == "2026-05-25"


def test_tabla_historica_vacia():
    vacio_pred = pd.DataFrame(columns=["fecha_objetivo", "hora_decision", "pico_pred", "p10", "p90"])
    vacio_obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    assert export.construir_tabla_historica(vacio_pred, vacio_obs) == []
