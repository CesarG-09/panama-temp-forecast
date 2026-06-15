# panama-temp-forecast 🌡️

Predicción auto-mejorable de la temperatura máxima diaria en Ciudad de Panamá
(estación **MPMG – Marcos A. Gelabert / Albrook**).

Cada día, un workflow de GitHub Actions: recolecta el máximo observado, evalúa
las predicciones pasadas (acierto/fallo), re-ajusta el modelo con corrección de
sesgo, predice los próximos 7 días y publica todo en un dashboard.

**Dashboard:** https://CesarG-09.github.io/panama-temp-forecast/

## Cómo funciona

`recolectar → evaluar → ajustar → predecir → exportar` (ver `src/pipeline.py`).
El modelo (`src/model.py`) es una climatología por día-del-año + anomalía
reciente + corrección de sesgo, detrás de una interfaz `ajustar/predecir`
intercambiable por algo más avanzado sin tocar el resto.

## Puesta en marcha

1. **Obtener la API key:** abre `https://www.wunderground.com/history/daily/pa/panama-city/MPMG`,
   abre las herramientas de desarrollo → pestaña *Network* → filtra `historical.json`,
   y copia el valor del parámetro `apiKey` de la petición.
2. **Guardar el secret:** repo → Settings → Secrets and variables → Actions →
   `New repository secret` → nombre `WUNDERGROUND_API_KEY`.
3. **Habilitar Pages:** Settings → Pages → Source: *GitHub Actions*.
4. **Cargar el histórico:** Actions → *Backfill histórico* → *Run workflow*
   (deja `2020-01-01`). Tarda según el rango.
5. **Listo:** el *Pipeline diario* corre solo cada día a las 12:00 UTC.

## Desarrollo local

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m pytest -v            # tests
export WUNDERGROUND_API_KEY=...  # (Windows: $env:WUNDERGROUND_API_KEY="...")
python -m src.pipeline         # corre el pipeline una vez
```

## Estructura

- `src/` — código del pipeline (scraper, model, evaluate, export, pipeline, backfill)
- `data/` — CSV versionados (observaciones, predicciones, evaluación)
- `docs/` — dashboard estático (GitHub Pages)
- `.github/workflows/` — automatización (diario + backfill)
- `docs/superpowers/` — spec de diseño y este plan
