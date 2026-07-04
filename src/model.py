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


def _matriz(fuente) -> pd.DataFrame:
    """Selecciona las columnas de features y las castea a float.

    El cast convierte `None` en `NaN` y garantiza dtype numérico: LightGBM
    rechaza columnas `object` (p. ej. `forecast_max` nulo en backfill) pero
    sí maneja `NaN` como valor faltante de forma nativa.
    """
    return fuente[FEATURE_COLS].astype(float)


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
        self.q_hat: float = 0.0

    def ajustar(self, set_entrenamiento: pd.DataFrame) -> "ModeloPico":
        X = _matriz(set_entrenamiento)
        y = set_entrenamiento["target"]
        for nombre, alpha in _CUANTILES.items():
            m = lgb.LGBMRegressor(alpha=alpha, **_PARAMS)
            m.fit(X, y)
            self._modelos[nombre] = m
        return self

    def predecir(self, fila: dict) -> tuple:
        X = _matriz(pd.DataFrame([{c: fila.get(c) for c in FEATURE_COLS}]))
        vals = {n: float(m.predict(X)[0]) for n, m in self._modelos.items()}
        # Calibración conformal: ensancha (o encoge) el intervalo, no el p50.
        lo = vals["p10"] - self.q_hat
        hi = vals["p90"] + self.q_hat
        # Garantiza monotonía p10 <= p50 <= p90.
        p10, p50, p90 = sorted((lo, vals["p50"], hi))
        return round(p10, 1), round(p50, 1), round(p90, 1)

    def guardar(self, ruta) -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        payload = {n: m.booster_.model_to_string() for n, m in self._modelos.items()}
        payload["calibracion"] = {"q_hat": self.q_hat}
        ruta.write_text(json.dumps(payload))

    @classmethod
    def cargar(cls, ruta) -> "ModeloPico":
        payload = json.loads(Path(ruta).read_text())
        obj = cls()
        # Se saca antes del loop: no es un booster (y un archivo v1 no la trae).
        calib = payload.pop("calibracion", None) or {}
        obj.q_hat = float(calib.get("q_hat", 0.0))
        for n, s in payload.items():
            obj._modelos[n] = _BoosterWrap(lgb.Booster(model_str=s))
        return obj


def entrenar_calibrado(set_ent: pd.DataFrame,
                       dias_calibracion: int = 45) -> ModeloPico:
    """Entrena con calibración conformal (CQR) del intervalo p10-p90.

    Aparta los últimos `dias_calibracion` días como calibración, entrena con el
    resto y mide cuánto hay que ensanchar el intervalo para cubrir ~80% real
    (q_hat). Después re-entrena con todos los datos (la recencia importa) y
    conserva ese q_hat: leve sobre-cobertura, preferible a un intervalo corto.
    Sin días suficientes devuelve el modelo sin calibrar (q_hat = 0).
    """
    fechas = sorted(set_ent["fecha_objetivo"].unique())
    if len(fechas) <= dias_calibracion * 2:
        return ModeloPico().ajustar(set_ent)
    corte = fechas[-dias_calibracion]
    base = ModeloPico().ajustar(set_ent[set_ent["fecha_objetivo"] < corte])
    calib = set_ent[set_ent["fecha_objetivo"] >= corte]

    scores = []
    for _, r in calib.iterrows():
        p10, _, p90 = base.predecir(r.to_dict())
        y = float(r["target"])
        scores.append(max(p10 - y, y - p90))
    alpha = 0.2
    nivel = min(1.0, (1 - alpha) * (1 + 1 / len(scores)))
    q_hat = float(pd.Series(scores).quantile(nivel))

    final = ModeloPico().ajustar(set_ent)
    final.q_hat = q_hat
    return final
