import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, evaluate


def construir_payload(observaciones: pd.DataFrame, predicciones: pd.DataFrame,
                      evaluacion: pd.DataFrame, hoy: str) -> dict:
    futuras = predicciones[predicciones["fecha_objetivo"] > hoy]
    futuras = (futuras.sort_values("fecha_prediccion")
                      .drop_duplicates("fecha_objetivo", keep="last")
                      .sort_values("fecha_objetivo"))
    return {
        "generado": datetime.now(ZoneInfo(config.TZ)).isoformat(),
        "historico": observaciones.sort_values("fecha").to_dict("records"),
        "predicciones": futuras[["fecha_objetivo", "temp_max_pred_c"]].to_dict("records"),
        "metricas": evaluate.metricas(evaluacion),
        "evaluaciones": evaluacion.sort_values("fecha_objetivo").tail(30).to_dict("records"),
    }


def exportar(ruta: Path, payload: dict) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
