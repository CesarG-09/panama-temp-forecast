import pandas as pd
from src import storage


def test_upsert_crea_y_actualiza_sin_duplicar(tmp_path):
    ruta = tmp_path / "obs.csv"
    cols = ["fecha", "temp_max_c"]

    storage.upsert_rows(ruta, [{"fecha": "2020-01-01", "temp_max_c": 31.0}], cols, ["fecha"])
    df = storage.upsert_rows(ruta, [{"fecha": "2020-01-01", "temp_max_c": 32.5}], cols, ["fecha"])

    assert len(df) == 1
    assert df.iloc[0]["temp_max_c"] == 32.5


def test_upsert_ordena_por_clave(tmp_path):
    ruta = tmp_path / "obs.csv"
    cols = ["fecha", "temp_max_c"]
    storage.upsert_rows(ruta, [
        {"fecha": "2020-01-03", "temp_max_c": 33.0},
        {"fecha": "2020-01-01", "temp_max_c": 31.0},
    ], cols, ["fecha"])
    df = storage.read_csv(ruta, cols)
    assert list(df["fecha"]) == ["2020-01-01", "2020-01-03"]


def test_read_csv_vacio_devuelve_columnas(tmp_path):
    df = storage.read_csv(tmp_path / "no_existe.csv", ["fecha", "temp_max_c"])
    assert list(df.columns) == ["fecha", "temp_max_c"]
    assert len(df) == 0
