import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config


def construir_pasadas_vs_real(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                              n_dias: int = 30) -> list[dict]:
    """Por día con pico real: predicción de la mañana (hora de decisión mínima),
    su banda, y la predicción final (hora máxima), contra el pico real.

    Devuelve los últimos `n_dias` días, ascendente por fecha.
    """
    if len(predicciones) == 0 or len(observaciones) == 0:
        return []
    real = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for fecha, grupo in predicciones.groupby("fecha_objetivo"):
        if fecha not in real:
            continue
        g = grupo.sort_values("hora_decision")
        manana, final = g.iloc[0], g.iloc[-1]
        filas.append({
            "fecha": fecha,
            "real": round(float(real[fecha]), 1),
            "manana_p50": round(float(manana["pico_pred"]), 1),
            "manana_p10": round(float(manana["p10"]), 1),
            "manana_p90": round(float(manana["p90"]), 1),
            "final_p50": round(float(final["pico_pred"]), 1),
        })
    filas.sort(key=lambda r: r["fecha"])
    return filas[-n_dias:]


def construir_payload(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                      evaluacion: pd.DataFrame, hoy: str,
                      curva_hoy: list | None = None,
                      generado: str | None = None,
                      temp_actual: dict | None = None) -> dict:
    hoy_preds = predicciones[predicciones["fecha_objetivo"] == hoy] \
        .sort_values("hora_decision")

    pico_hoy = None
    convergencia = []
    if len(hoy_preds):
        ult = hoy_preds.iloc[-1]
        pico_hoy = {"pico_pred": float(ult["pico_pred"]),
                    "p10": float(ult["p10"]), "p90": float(ult["p90"]),
                    "hora_decision": int(ult["hora_decision"])}
        convergencia = [{"hora_decision": int(r["hora_decision"]),
                         "pico_pred": float(r["pico_pred"]),
                         "p10": float(r["p10"]), "p90": float(r["p90"])}
                        for _, r in hoy_preds.iterrows()]

    error_por_hora = []
    if len(evaluacion):
        g = evaluacion.assign(abs_err=evaluacion["error_c"].abs()) \
            .groupby("hora_decision")["abs_err"].mean().reset_index()
        error_por_hora = [{"hora_decision": int(r["hora_decision"]),
                           "error_medio_abs": round(float(r["abs_err"]), 2)}
                          for _, r in g.iterrows()]

    observados = [{"fecha": r["fecha"], "temp_max_c": float(r["temp_max_c"])}
                  for _, r in observaciones.tail(30).iterrows()]

    if generado is None:
        generado = datetime.now(ZoneInfo(config.TZ)).isoformat(timespec="minutes")

    return {
        "hoy": hoy,
        "generado": generado,
        "temp_actual": temp_actual,
        "pico_hoy": pico_hoy,
        "curva_hoy": curva_hoy or [],
        "convergencia_hoy": convergencia,
        "error_por_hora": error_por_hora,
        "observados_recientes": observados,
    }


def exportar(ruta, payload: dict) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
