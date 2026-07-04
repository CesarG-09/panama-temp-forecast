from src import backfill, config, dataset, storage
from src.model import entrenar_calibrado


def correr(incremental: bool = True) -> None:
    # 1. Traer/actualizar los días recientes antes de reentrenar.
    if incremental:
        backfill.actualizar_reciente()

    # 2. Ensamblar el set y entrenar.
    hist = storage.read_hourly()
    obs = storage.read_observations()
    fcst = storage.read_forecast()
    forecast_por_fecha = (dict(zip(fcst["fecha"], fcst["forecast_max"]))
                          if len(fcst) else {})
    mpmg = storage.read_mpmg_hourly()
    set_ent = dataset.construir_set(hist, obs, forecast_por_fecha,
                                    mpmg_horario=mpmg)
    if len(set_ent) == 0:
        raise RuntimeError("Set de entrenamiento vacío; ¿falta backfill?")

    modelo = entrenar_calibrado(set_ent)
    modelo.guardar(config.ruta_modelo())


if __name__ == "__main__":
    correr()
