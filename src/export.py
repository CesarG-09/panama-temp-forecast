import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config


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
