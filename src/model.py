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
