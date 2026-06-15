import pandas as pd


class Climatologia:
    """Media del máximo para cada día-del-año, con ventana circular ±N días."""

    def __init__(self, ventana_dias: int = 7):
        self.ventana = ventana_dias
        self._hist: pd.DataFrame | None = None
        self._media_global: float = 0.0

    def ajustar(self, hist: pd.DataFrame) -> "Climatologia":
        df = hist.copy()
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["doy"] = df["fecha"].dt.dayofyear
        self._hist = df
        self._media_global = float(df["temp_max_c"].mean())
        return self

    def _media_doy(self, doy: int) -> float:
        difs = ((self._hist["doy"] - doy + 182) % 365) - 182
        vals = self._hist.loc[difs.abs() <= self.ventana, "temp_max_c"]
        if len(vals) == 0:
            return self._media_global
        return float(vals.mean())

    def predecir(self, fechas) -> list[float]:
        return [round(self._media_doy(pd.Timestamp(f).dayofyear), 1) for f in fechas]


class Predictor:
    """Climatología + anomalía reciente + corrección de sesgo (lazo de mejora)."""

    def __init__(self, clima: Climatologia | None = None,
                 dias_anomalia: int = 3, dias_sesgo: int = 14,
                 decaimiento: float = 0.7):
        self.clima = clima or Climatologia()
        self.dias_anomalia = dias_anomalia
        self.dias_sesgo = dias_sesgo
        self.decaimiento = decaimiento
        self.anomalia = 0.0
        self.sesgo = 0.0

    def ajustar(self, hist: pd.DataFrame, evaluacion: pd.DataFrame | None = None):
        self.clima.ajustar(hist)

        h = hist.copy()
        h["fecha"] = pd.to_datetime(h["fecha"])
        h = h.sort_values("fecha")
        ult = h.tail(self.dias_anomalia)
        if len(ult):
            base = self.clima.predecir(ult["fecha"].tolist())
            self.anomalia = float((ult["temp_max_c"].to_numpy() - base).mean())

        if evaluacion is not None and len(evaluacion):
            self.sesgo = float(evaluacion.tail(self.dias_sesgo)["error_c"].mean())

        return self

    def predecir(self, fechas) -> list[float]:
        # La anomalía reciente decae con el horizonte (la persistencia se diluye:
        # el día i-ésimo conserva anomalia * decaimiento**i); el sesgo no decae.
        base = self.clima.predecir(fechas)
        return [round(b + self.anomalia * (self.decaimiento ** i) - self.sesgo, 1)
                for i, b in enumerate(base)]
