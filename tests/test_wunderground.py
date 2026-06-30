from datetime import date

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


def test_parse_curva_intradia_toma_maximo_por_hora_local():
    # 1577880000 = 2020-01-01 12:00 UTC = 07:00 Panamá (UTC-5)
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},   # 07:00 -> hora 7
        {"valid_time_gmt": 1577881800, "temp": 30.0},   # 07:30 -> hora 7 (mayor)
        {"valid_time_gmt": 1577883600, "temp": 31.0},   # 08:00 -> hora 8
    ]}
    curva = wunderground.parse_curva_intradia(payload, date(2020, 1, 1))
    assert curva == [{"hora": 7, "temp_c": 30.0}, {"hora": 8, "temp_c": 31.0}]


def test_parse_curva_intradia_excluye_otras_fechas_y_nulos():
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},   # 2020-01-01 07:00 Panamá
        {"valid_time_gmt": 1577966400, "temp": 33.0},   # 2020-01-02 07:00 Panamá (otra fecha)
        {"valid_time_gmt": 1577883600, "temp": None},   # nulo, se ignora
    ]}
    curva = wunderground.parse_curva_intradia(payload, date(2020, 1, 1))
    assert curva == [{"hora": 7, "temp_c": 28.0}]


def test_parse_actual_toma_la_observacion_mas_reciente():
    # Misma fecha; debe quedarse con la última (valid_time_gmt mayor).
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},   # 07:00 Panamá
        {"valid_time_gmt": 1577883600, "temp": 31.0},   # 08:00 Panamá (más reciente)
    ]}
    actual = wunderground.parse_actual(payload, date(2020, 1, 1))
    assert actual == {"temp_c": 31.0, "hora_local": "08:00"}


def test_parse_actual_sin_datos_de_la_fecha_devuelve_none():
    payload = {"observations": [
        {"valid_time_gmt": 1577966400, "temp": 33.0},   # 2020-01-02, otra fecha
        {"valid_time_gmt": 1577883600, "temp": None},   # nulo
    ]}
    assert wunderground.parse_actual(payload, date(2020, 1, 1)) is None


def test_parse_horas_pico_hora_del_maximo_por_dia():
    # 1577880000 = 2020-01-01 07:00 Panamá; +3600=08:00; +7200=09:00
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},   # 07:00
        {"valid_time_gmt": 1577883600, "temp": 31.0},   # 08:00  <- máximo
        {"valid_time_gmt": 1577887200, "temp": 30.0},   # 09:00
    ]}
    assert wunderground.parse_horas_pico(payload) == {"2020-01-01": 8}


def test_parse_horas_pico_empate_toma_la_hora_mas_temprana():
    payload = {"observations": [
        {"valid_time_gmt": 1577887200, "temp": 31.0},   # 09:00 (empate, más tarde)
        {"valid_time_gmt": 1577883600, "temp": 31.0},   # 08:00 (empate, más temprano)
    ]}
    assert wunderground.parse_horas_pico(payload) == {"2020-01-01": 8}


def test_parse_horas_pico_ignora_nulos():
    payload = {"observations": [
        {"valid_time_gmt": 1577883600, "temp": None},
        {"valid_time_gmt": 1577887200, "temp": 30.0},   # 09:00
    ]}
    assert wunderground.parse_horas_pico(payload) == {"2020-01-01": 9}
