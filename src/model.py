import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from src.features import FEATURE_COLS

_CUANTILES = {"p10": 0.10, "p50": 0.50, "p90": 0.90}
_PARAMS = {
    "objective": "quantile",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "verbose": -1,
}


class _BoosterWrap:
    """Envuelve un Booster cargado para exponer .predict como el regresor."""

    def __init__(self, booster: lgb.Booster):
        self._b = booster

    def predict(self, X):
        return self._b.predict(X)


class ModeloPico:
    """Tres regresores LightGBM de cuantiles (p10/p50/p90) tras ajustar/predecir."""

    def __init__(self):
        self._modelos: dict = {}

    def ajustar(self, set_entrenamiento: pd.DataFrame) -> "ModeloPico":
        X = set_entrenamiento[FEATURE_COLS]
        y = set_entrenamiento["target"]
        for nombre, alpha in _CUANTILES.items():
            m = lgb.LGBMRegressor(alpha=alpha, **_PARAMS)
            m.fit(X, y)
            self._modelos[nombre] = m
        return self

    def predecir(self, fila: dict) -> tuple:
        X = pd.DataFrame([{c: fila.get(c) for c in FEATURE_COLS}])[FEATURE_COLS]
        vals = {n: float(m.predict(X)[0]) for n, m in self._modelos.items()}
        # Garantiza monotonía p10 <= p50 <= p90.
        p10, p50, p90 = sorted((vals["p10"], vals["p50"], vals["p90"]))
        return round(p10, 1), round(p50, 1), round(p90, 1)

    def guardar(self, ruta) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        payload = {n: m.booster_.model_to_string() for n, m in self._modelos.items()}
        ruta.write_text(json.dumps(payload))

    @classmethod
    def cargar(cls, ruta) -> "ModeloPico":
        payload = json.loads(Path(ruta).read_text())
        obj = cls()
        for n, s in payload.items():
            obj._modelos[n] = _BoosterWrap(lgb.Booster(model_str=s))
        return obj
