from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from src import config


def parse_historical_json(payload: dict) -> list[dict]:
    """Agrupa observaciones por día (hora local de Panamá) y toma el máximo."""
    tz = ZoneInfo(config.TZ)
    por_dia: dict = defaultdict(list)
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dia = datetime.fromtimestamp(ts, tz=tz).date()
        por_dia[dia].append(temp)
    return [
        {"fecha": dia.isoformat(), "temp_max_c": round(max(temps), 1)}
        for dia, temps in sorted(por_dia.items())
    ]
