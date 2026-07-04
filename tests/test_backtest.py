import numpy as np
import pandas as pd

from src import backtest, storage


def _sembrar(tmp_path, monkeypatch, n_dias=120):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    rng = np.random.default_rng(3)
    horas, obs = [], []
    base = pd.Timestamp("2025-01-01")
    for d in range(n_dias):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in range(17):
            horas.append({"timestamp": f"{fecha}T{h:02d}:00",
                          "temp_c": 24 + h * (pico - 24) / 16,
                          "humedad": 80.0, "nubosidad": 30.0})
        obs.append({"fecha": fecha, "temp_max_c": round(pico, 1)})
    storage.upsert_hourly(horas)
    storage.upsert_observations(obs)


def test_backtest_evalua_meses_sin_fuga_temporal(tmp_path, monkeypatch):
    _sembrar(tmp_path, monkeypatch)
    res = backtest.correr(n_meses=2)
    # Solo evalúa los 2 últimos meses del dataset (mar-abr 2025).
    assert set(res["mes"]) == {"2025-03", "2025-04"}
    # Métricas razonables sobre datos sintéticos regulares.
    tabla = backtest.resumen(res)
    total = tabla.loc["TOTAL"]
    assert total["mae"] < 1.5
    assert 0.0 <= total["cobertura"] <= 1.0


def test_backtest_no_escribe_datos(tmp_path, monkeypatch):
    _sembrar(tmp_path, monkeypatch)
    antes = {p.name: p.stat().st_size for p in tmp_path.iterdir()}
    backtest.correr(n_meses=1)
    despues = {p.name: p.stat().st_size for p in tmp_path.iterdir()}
    assert antes == despues
