from datetime import date
from pathlib import Path

from src import scraper

HTML = (Path(__file__).parent / "fixtures" / "history_page.html").read_text()


def test_parse_history_html_devuelve_maximo_en_celsius():
    fecha = date(2020, 1, 1)
    fila = scraper.parse_history_html(HTML, fecha)
    # 92 °F = 33.3 °C
    assert fila == {"fecha": "2020-01-01", "temp_max_c": 33.3}


def test_f_a_c():
    assert scraper.f_a_c(32) == 0.0
    assert scraper.f_a_c(212) == 100.0
