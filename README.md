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
  - **Wunderground MPMG** — la *verdad*: el pico diario real (target del modelo).
- **Features (solo lo conocible hasta la hora H):** calendario (día-del-año
  seno/coseno, mes), máximo-hasta-ahora, temperatura actual y rezagos, tasa de
  subida, humedad, nubosidad y el forecast de Open-Meteo (feature nullable).

## Flujo (workflows de GitHub Actions)

- **`backfill.yml`** (manual) — carga el histórico horario (Open-Meteo) y los
  picos diarios (Wunderground) desde 2020.
- **`train.yml`** (nocturno, 06:00 UTC) — backfill incremental + reentrena los
  modelos y guarda `models/peak_model.txt`.
- **`hourly.yml`** (cada hora 11:00–21:00 UTC = 6am–4pm Panamá) — predice el pico
  de hoy, registra la predicción, evalúa los días cerrados y publica el dashboard.

## Puesta en marcha

1. **Secret de Wunderground:** repo → Settings → Secrets and variables → Actions →
   `New repository secret` → nombre `WUNDERGROUND_API_KEY`
   (ver instrucciones de la apiKey en el historial del proyecto).
2. **Habilitar Pages:** Settings → Pages → Source: *GitHub Actions*.
3. **Cargar el histórico:** Actions → *Backfill histórico* → *Run workflow*
   (deja `2020-01-01`).
4. **Entrenar:** Actions → *Entrenamiento nocturno* → *Run workflow* (o espera al cron).
5. **Listo:** la *Predicción horaria* corre sola en la franja diurna.

## Desarrollo local

```bash
pip install -r requirements.txt
python -m playwright install chromium   # solo si usas el respaldo de Wunderground
python -m pytest -v                      # tests

export WUNDERGROUND_API_KEY=...          # (Windows: $env:WUNDERGROUND_API_KEY="...")
python -m src.backfill 2020-01-01        # carga inicial
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
