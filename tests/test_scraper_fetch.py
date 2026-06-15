import json
from datetime import date
from pathlib import Path

import pytest

from src import scraper

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "historical_sample.json").read_text())


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_via_api_construye_url_y_parsea(monkeypatch):
    capturado = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["params"] = params
        return _FakeResp(FIXTURE)

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    monkeypatch.setenv("WUNDERGROUND_API_KEY", "clave-de-prueba")

    filas = scraper.fetch_via_api(date(2020, 1, 1), date(2020, 1, 2))

    assert capturado["params"]["apiKey"] == "clave-de-prueba"
    assert capturado["params"]["startDate"] == "20200101"
    assert capturado["params"]["endDate"] == "20200102"
    assert capturado["params"]["units"] == "m"
    assert filas[0] == {"fecha": "2020-01-01", "temp_max_c": 31.5}


def test_fetch_via_api_sin_clave_lanza(monkeypatch):
    monkeypatch.delenv("WUNDERGROUND_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="WUNDERGROUND_API_KEY"):
        scraper.fetch_via_api(date(2020, 1, 1), date(2020, 1, 2))
