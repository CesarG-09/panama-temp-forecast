import sys
from datetime import date, timedelta

from src import config, storage
from src.sources import openmeteo, wunderground


def correr(desde: date | None = None, hasta: date | None = None) -> None:
    desde = desde or config.FECHA_INICIO
    hasta = hasta or (date.today() - timedelta(days=1))

    # 1. Histórico horario (Open-Meteo) en bloques anuales para no pedir todo de una.
    bloque_ini = desde
    while bloque_ini <= hasta:
        bloque_fin = min(date(bloque_ini.year, 12, 31), hasta)
        filas = openmeteo.fetch_archivo(bloque_ini, bloque_fin)
        if filas:
            storage.upsert_hourly(filas)
        bloque_ini = date(bloque_ini.year + 1, 1, 1)

    # 2. Picos diarios reales (Wunderground MPMG).
    obs = wunderground.obtener_observaciones(desde, hasta)
    if obs:
        storage.upsert_observations(obs)


if __name__ == "__main__":
    desde = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    correr(desde=desde)
