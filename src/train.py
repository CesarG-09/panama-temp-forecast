from src import backfill, config, dataset, storage
from src.model import ModeloPico


def correr(incremental: bool = True) -> None:
    # 1. Traer/actualizar los días recientes antes de reentrenar.
    if incremental:
        backfill.actualizar_reciente()

    # 2. Ensamblar el set y entrenar.
    hist = storage.read_hourly()
    obs = storage.read_observations()
    set_ent = dataset.construir_set(hist, obs)
    if len(set_ent) == 0:
        raise RuntimeError("Set de entrenamiento vacío; ¿falta backfill?")

    modelo = ModeloPico().ajustar(set_ent)
    modelo.guardar(config.ruta_modelo())


if __name__ == "__main__":
    correr()
