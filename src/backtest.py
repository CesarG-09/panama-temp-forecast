"""Backtest rolling-origin mensual del modelo de pico.

Para cada uno de los últimos n meses con datos: entrena con todo lo anterior
al mes y predice cada (día, hora de decisión) del mes. Imprime MAE, sesgo,
acierto (<= UMBRAL_ACIERTO_C), cobertura y ancho del intervalo p10-p90.

Uso: python -m src.backtest [n_meses] [--sin-mpmg]
No escribe nada en data/ ni models/: es solo un harness de evaluación.
"""
import sys

import pandas as pd

from src import config, dataset, storage
from src.model import entrenar_calibrado

_MIN_FILAS_ENTRENAMIENTO = 100


def correr(n_meses: int = 6, con_mpmg: bool = True) -> pd.DataFrame:
    hist = storage.read_hourly()
    obs = storage.read_observations()
    fcst = storage.read_forecast()
    mpmg = storage.read_mpmg_hourly() if con_mpmg else None
    forecast_por_fecha = (dict(zip(fcst["fecha"], fcst["forecast_max"]))
                          if len(fcst) else {})
    total = dataset.construir_set(hist, obs, forecast_por_fecha,
                                  mpmg_horario=mpmg)
    if len(total) == 0:
        raise RuntimeError("Sin datos para el backtest; ¿falta backfill?")
    total = total.sort_values(["fecha_objetivo", "hora_decision"])

    meses = sorted(total["fecha_objetivo"].str.slice(0, 7).unique())[-n_meses:]
    filas = []
    for mes in meses:
        ent = total[total["fecha_objetivo"] < f"{mes}-01"]
        prueba = total[total["fecha_objetivo"].str.startswith(mes)]
        if len(ent) < _MIN_FILAS_ENTRENAMIENTO or len(prueba) == 0:
            print(f"{mes}: omitido (entrenamiento insuficiente: {len(ent)} filas)")
            continue
        modelo = entrenar_calibrado(ent)
        for _, r in prueba.iterrows():
            p10, p50, p90 = modelo.predecir(r.to_dict())
            filas.append({"mes": mes, "fecha": r["fecha_objetivo"],
                          "hora_decision": int(r["hora_decision"]),
                          "p10": p10, "pred": p50, "p90": p90,
                          "real": float(r["target"])})
    return pd.DataFrame(filas)


def _metricas(g: pd.DataFrame) -> pd.Series:
    err = g["pred"] - g["real"]
    return pd.Series({
        "n": len(g),
        "mae": err.abs().mean(),
        "sesgo": err.mean(),
        "acierto": (err.abs() <= config.UMBRAL_ACIERTO_C).mean(),
        "cobertura": ((g["real"] >= g["p10"]) & (g["real"] <= g["p90"])).mean(),
        "ancho": (g["p90"] - g["p10"]).mean(),
    })


def resumen(res: pd.DataFrame) -> pd.DataFrame:
    """Métricas por mes más la fila TOTAL agregada."""
    por_mes = res.groupby("mes").apply(_metricas, include_groups=False)
    por_mes.loc["TOTAL"] = _metricas(res)
    return por_mes.round(3)


def main(argv: list[str]) -> None:
    con_mpmg = "--sin-mpmg" not in argv
    pos = [a for a in argv if not a.startswith("--")]
    n_meses = int(pos[0]) if pos else 6
    res = correr(n_meses=n_meses, con_mpmg=con_mpmg)
    if len(res) == 0:
        print("Backtest sin resultados.")
        return
    etiqueta = "con features MPMG" if con_mpmg else "SIN features MPMG"
    print(f"\n=== Backtest {etiqueta} — por mes ===")
    print(resumen(res).to_string())
    print("\n=== Por hora de decisión (todos los meses) ===")
    por_hora = res.groupby("hora_decision").apply(_metricas,
                                                  include_groups=False)
    print(por_hora.round(3).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
