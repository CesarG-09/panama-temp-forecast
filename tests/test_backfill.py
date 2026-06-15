from datetime import date

from src import backfill


def test_rangos_mensuales_cubre_desde_hasta():
    rangos = backfill.rangos_mensuales(date(2020, 1, 1), date(2020, 3, 15))
    assert rangos[0] == (date(2020, 1, 1), date(2020, 1, 31))
    assert rangos[1] == (date(2020, 2, 1), date(2020, 2, 29))  # 2020 bisiesto
    assert rangos[-1] == (date(2020, 3, 1), date(2020, 3, 15))


def test_correr_backfill_acumula_observaciones(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))

    def fake_fetch(desde, hasta):
        return [{"fecha": desde.isoformat(), "temp_max_c": 31.0}]

    monkeypatch.setattr(backfill.scraper, "obtener_observaciones", fake_fetch)

    backfill.correr(date(2020, 1, 1), date(2020, 3, 15))

    from src import storage
    obs = storage.read_observations()
    assert len(obs) == 3  # un dato por cada rango mensual (fixture simplificado)
