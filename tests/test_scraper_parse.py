import json
from pathlib import Path

from src import scraper

FIXTURE = Path(__file__).parent / "fixtures" / "historical_sample.json"


def test_parse_agrupa_por_dia_y_toma_el_maximo():
    payload = json.loads(FIXTURE.read_text())
    filas = scraper.parse_historical_json(payload)

    # Epochs caen el 2020-01-01 y 2020-01-02 en hora de Panamá (UTC-5)
    assert filas == [
        {"fecha": "2020-01-01", "temp_max_c": 31.5},
        {"fecha": "2020-01-02", "temp_max_c": 33.2},
    ]


def test_parse_ignora_temperaturas_nulas_y_payload_vacio():
    assert scraper.parse_historical_json({"observations": []}) == []
    assert scraper.parse_historical_json({}) == []
