from datetime import date

from src import scraper


def test_obtener_usa_api_cuando_funciona(monkeypatch):
    monkeypatch.setattr(scraper, "fetch_via_api",
                        lambda d, h: [{"fecha": "2020-01-01", "temp_max_c": 31.5}])
    llamado = {"browser": False}
    monkeypatch.setattr(scraper, "fetch_via_browser",
                        lambda f: llamado.__setitem__("browser", True) or [])

    filas = scraper.obtener_observaciones(date(2020, 1, 1), date(2020, 1, 1))

    assert filas == [{"fecha": "2020-01-01", "temp_max_c": 31.5}]
    assert llamado["browser"] is False


def test_obtener_cae_a_browser_si_api_falla(monkeypatch):
    def api_rota(d, h):
        raise RuntimeError("api caída")

    monkeypatch.setattr(scraper, "fetch_via_api", api_rota)
    monkeypatch.setattr(scraper, "fetch_via_browser",
                        lambda f: [{"fecha": f.isoformat(), "temp_max_c": 33.3}])

    filas = scraper.obtener_observaciones(date(2020, 1, 1), date(2020, 1, 2))

    assert {"fecha": "2020-01-01", "temp_max_c": 33.3} in filas
    assert {"fecha": "2020-01-02", "temp_max_c": 33.3} in filas
