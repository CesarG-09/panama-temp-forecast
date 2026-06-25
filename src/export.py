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


def construir_evolucion(evaluacion: pd.DataFrame, ventana: int = 7,
                        umbral: float = config.UMBRAL_ACIERTO_C) -> list[dict]:
    """Serie temporal de desempeño: error absoluto diario (mañana=hora mínima,
    final=hora máxima), su media móvil de `ventana` días, y la tasa de acierto
    móvil (fracción de días con |error| <= `umbral`). Ascendente por fecha.
    """
    if len(evaluacion) == 0:
        return []
    ev = evaluacion.copy()
    ev["abs_err"] = ev["error_c"].abs()
    por_dia = []
    for fecha, grupo in ev.groupby("fecha_objetivo"):
        g = grupo.sort_values("hora_decision")
        em, ef = float(g.iloc[0]["abs_err"]), float(g.iloc[-1]["abs_err"])
        por_dia.append({"fecha": fecha,
                        "err_manana": round(em, 2), "err_final": round(ef, 2),
                        "hit_manana": 1.0 if em <= umbral else 0.0,
                        "hit_final": 1.0 if ef <= umbral else 0.0})
    df = pd.DataFrame(por_dia).sort_values("fecha").reset_index(drop=True)

    def rolling(col):
        return df[col].rolling(ventana, min_periods=1).mean()

    df["mae7_manana"] = rolling("err_manana").round(2)
    df["mae7_final"] = rolling("err_final").round(2)
    df["acierto7_manana"] = rolling("hit_manana").round(3)
    df["acierto7_final"] = rolling("hit_final").round(3)
    return [{"fecha": r["fecha"],
             "err_manana": float(r["err_manana"]), "err_final": float(r["err_final"]),
             "mae7_manana": float(r["mae7_manana"]), "mae7_final": float(r["mae7_final"]),
             "acierto7_manana": float(r["acierto7_manana"]),
             "acierto7_final": float(r["acierto7_final"])}
            for _, r in df.iterrows()]


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
        "pasadas_vs_real": construir_pasadas_vs_real(predicciones, observaciones),
        "evolucion_modelo": construir_evolucion(evaluacion),
    }


def exportar(ruta, payload: dict) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
