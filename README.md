# panama-temp-forecast 🌡️

Predicción por **Machine Learning** del **pico (temperatura máxima) de HOY** en
Ciudad de Panamá (estación **MPMG – Marcos A. Gelabert / Albrook**), refinada
**cada hora** con los datos observados a lo largo del día.

La salida de cada corrida es el **pico estimado** (p50) más una **banda de
confianza** [p10, p90] que se estrecha conforme avanza el día.

**Dashboard:** https://CesarG-09.github.io/panama-temp-forecast/

## Cómo funciona

- **Modelo:** tres regresores **LightGBM por cuantiles** (p10/p50/p90) detrás de
  una interfaz `ajustar/predecir` intercambiable (`src/model.py`).
- **Fuentes de datos:**
  - **Open-Meteo** — motor de datos del ML: histórico horario (archivo ERA5 desde
    2020) para entrenar, intradía de hoy (features en vivo) y forecast del día.
    El **pico diario histórico** (target) se deriva del máximo de ese horario,
    de modo que el backfill no depende de scraping día-a-día.
  - **Wunderground MPMG** — la *verdad de la estación* en el lazo en curso: en
    cada reentrenamiento nocturno su pico real sobreescribe el target de los
    días recientes (si la API responde).
- **Features (solo lo conocible hasta la hora H):** calendario (día-del-año
  seno/coseno, mes), máximo-hasta-ahora, temperatura actual y rezagos, tasa de
  subida, humedad, nubosidad y el forecast de Open-Meteo (feature nullable).

## Flujo (workflows de GitHub Actions)

- **`backfill.yml`** (manual) — carga el histórico horario (Open-Meteo) y deriva
  de él el pico diario histórico, desde 2020. Rápido: sin navegador día-a-día.
- **`train.yml`** (nocturno, 06:00 UTC) — actualiza los días recientes
  (Open-Meteo + verdad de Wunderground), reentrena los modelos y guarda
  `models/peak_model.txt`.
- **`hourly.yml`** (cada hora 11:00–21:00 UTC = 6am–4pm Panamá) — predice el pico
  de hoy, registra la predicción, evalúa los días cerrados y publica el dashboard.
  El `cron` de GitHub es *best-effort*: en horas de carga descarta o retrasa los
  disparos, así que la fuente **puntual** es un cron externo vía `workflow_dispatch`
  (ver [Disparo puntual](#disparo-puntual-cron-externo)); el `cron` queda de respaldo.

## Puesta en marcha

1. **Secret de Wunderground (opcional pero recomendado):** repo → Settings →
   Secrets and variables → Actions → `New repository secret` → nombre
   `WUNDERGROUND_API_KEY`. Si falta o caduca, el target cae al derivado de Open-Meteo.
2. **Habilitar Pages:** Settings → Pages → Source: *GitHub Actions*.
3. **Cargar el histórico:** Actions → *Backfill histórico* → *Run workflow*
   (deja `2020-01-01`).
4. **Entrenar:** Actions → *Entrenamiento nocturno* → *Run workflow* (o espera al cron).
5. **Listo:** la *Predicción horaria* corre sola en la franja diurna.

## Disparo puntual (cron externo)

Los `schedule` de GitHub Actions **no son puntuales**: en horas de carga retrasan
los disparos 10–30+ min o los descartan. Para que el dashboard se actualice a la
hora exacta, un servicio cron externo invoca `hourly.yml` por la API (un
`workflow_dispatch` **sí** se ejecuta de inmediato, no se descarta). El `cron` del
workflow se deja como respaldo gratuito.

**1. Crear un token de acceso (fine-grained PAT)** — github.com → *Settings* →
*Developer settings* → *Personal access tokens* → *Fine-grained tokens* →
*Generate new token*:
- *Resource owner:* `CesarG-09`
- *Repository access:* *Only select repositories* → `panama-temp-forecast`
- *Permissions* → *Repository permissions* → **Actions: Read and write**
  (*Metadata: Read* se añade solo).
- *Expiration:* lo que prefieras (al caducar hay que regenerarlo).
- Copia el token: solo se muestra una vez. **No lo subas al repo**; vive solo en
  el servicio externo.

**2. Crear el job en un cron externo** (p. ej. [cron-job.org](https://cron-job.org),
gratis y puntual al minuto; sirve cualquiera que haga POST con cabeceras y cuerpo):
- **Método:** `POST`
- **URL:** `https://api.github.com/repos/CesarG-09/panama-temp-forecast/actions/workflows/hourly.yml/dispatches`
- **Cabeceras:**
  - `Accept: application/vnd.github+json`
  - `Authorization: Bearer EL_TOKEN`
  - `X-GitHub-Api-Version: 2022-11-28`
- **Cuerpo (JSON):** `{"ref":"main"}`
- **Horario:** cada hora **de 6:00 a 16:00, zona horaria `America/Panama`**
  (cron-job.org permite elegir la zona; si solo acepta UTC, usa 11:00–21:00).

Una respuesta `204 No Content` significa que el disparo se aceptó. Verifica en
*Actions* que la corrida aparece con evento `workflow_dispatch`.

## Desarrollo local

```bash
pip install -r requirements.txt
python -m playwright install chromium   # solo si usas el respaldo de Wunderground
python -m pytest -v                      # tests

python -m src.backfill 2020-01-01        # carga inicial (Open-Meteo)
python -m src.train                      # entrena el modelo
python -m src.predict                    # una corrida de predicción
```

## Estructura

- `src/` — código: `sources/` (openmeteo, wunderground), `features`, `dataset`,
  `model`, `train`, `predict`, `backfill`, `evaluate`, `export`, `storage`, `config`.
- `data/` — CSV versionados: `hourly_history.csv` (entrenamiento), `observations.csv`
  (picos reales), `predictions.csv` (predicciones horarias), `evaluation.csv`.
- `models/` — modelo entrenado versionado.
- `docs/` — dashboard estático (GitHub Pages).
- `.github/workflows/` — automatización (backfill + entrenamiento + horario).
- `docs/superpowers/` — spec de diseño y plan de implementación.
