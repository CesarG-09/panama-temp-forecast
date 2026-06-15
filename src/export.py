import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, evaluate


def _sanear(valor):
    """Convierte NaN/inf en None para producir JSON siempre válido.

    En arranque en frío (sin observaciones) el modelo devuelve NaN; sin esto,
    json.dumps emitiría tokens `NaN` que rompen el parseo del dashboard.
    """
    if isinstance(valor, dict):
        return {k: _sanear(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sanear(v) for v in valor]
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor


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
    # allow_nan=False garantiza que un NaN no saneado falle ruidosamente
    ruta.write_text(json.dumps(_sanear(payload), ensure_ascii=False, indent=2,
                              allow_nan=False))
