import calendar
from datetime import date

from src import config, scraper, storage


def rangos_mensuales(desde: date, hasta: date) -> list[tuple[date, date]]:
    rangos = []
    cursor = desde
    while cursor <= hasta:
        ultimo_dia = calendar.monthrange(cursor.year, cursor.month)[1]
        fin_mes = date(cursor.year, cursor.month, ultimo_dia)
        rangos.append((cursor, min(fin_mes, hasta)))
        cursor = fin_mes.replace(day=ultimo_dia)
        cursor = date(cursor.year + (cursor.month // 12),
                      (cursor.month % 12) + 1, 1)
    return rangos


def correr(desde: date | None = None, hasta: date | None = None) -> None:
    desde = desde or config.FECHA_INICIO
    hasta = hasta or date.today()
    for ini, fin in rangos_mensuales(desde, hasta):
        filas = scraper.obtener_observaciones(ini, fin)
        if filas:
            storage.upsert_observations(filas)
        print(f"Backfill {ini}..{fin}: {len(filas)} días")


if __name__ == "__main__":
    correr()
