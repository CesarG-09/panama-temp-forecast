from src.sources import wunderground


def test_parse_historical_json_agrupa_por_dia_y_toma_maximo():
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},
        {"valid_time_gmt": 1577883600, "temp": 31.0},
    ]}
    filas = wunderground.parse_historical_json(payload)
    assert len(filas) == 1
    assert filas[0]["temp_max_c"] == 31.0


def test_f_a_c_convierte_fahrenheit():
    assert wunderground.f_a_c(89.6) == 32.0
