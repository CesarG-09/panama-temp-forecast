# Diseño: panama-temp-forecast → ML del pico diario

**Fecha:** 2026-06-16
**Estado:** Aprobado (pendiente de revisión del spec escrito)
**Rama:** `ml-pico-diario`

## 1. Objetivo

Predecir la **temperatura pico (máxima) de HOY** en la estación MPMG
(Marcos A. Gelabert / Albrook, Ciudad de Panamá), refinando la predicción
**cada hora** durante el día con datos intradía recolectados en vivo.

Cada predicción entrega:
- **Pico estimado** del día (°C).
- **Banda de confianza** [p10, p90] que se **estrecha conforme avanza el día**
  (más horas observadas → menos incertidumbre).

Esto reemplaza el sistema actual (climatología heurística + pronóstico a 7 días).
El nuevo foco es una sola predicción —el pico de hoy— que mejora hora a hora.

## 2. Decisiones tomadas

| Tema | Decisión |
|------|----------|
| Tipo de modelo | Gradient Boosting (LightGBM), regresión por cuantiles |
| Alcance | Solo el pico de HOY (se retira el pronóstico a 7 días) |
| Cadencia de recolección | Cada 1h en franja diurna (~6am–4pm Panamá) |
| Fuente de la "verdad" (target) | Wunderground MPMG |
| Motor de datos del ML | Open-Meteo (histórico horario + intradía + forecast) |
| Backfill | Desde 2020-01-01 |
| Salida | Pico (p50) + banda [p10, p90], registrada cada hora |
| Entrega | Rama nueva + PR (no commit directo a `main`) |

## 3. Roles de las fuentes de datos

### Wunderground MPMG — la *verdad*
- Provee el **pico diario real observado**, que es el **target** del modelo y el
  valor que se reporta y se evalúa.
- Continúa el `data/observations.csv` existente (formato `fecha, temp_max_c`).
- Se sigue obteniendo con el `scraper.py` actual (API `historical.json` con
  respaldo Playwright).

### Open-Meteo — el *motor de datos del ML*
Gratis, sin API key, uso no comercial. Tres usos:
1. **Archivo histórico horario** (`archive-api.open-meteo.com`, ERA5, desde 2020):
   base para construir el set de entrenamiento.
2. **Intradía de hoy** (`api.open-meteo.com` forecast con `past_days`): temperatura
   hora a hora, humedad relativa, nubosidad → los features "en vivo".
3. **Forecast del día** (máxima diaria pronosticada para hoy): feature predictivo.

Coordenadas: lat ≈ 8.973, lon ≈ -79.556. Zona horaria `America/Panama` (UTC-5, sin DST).

## 4. Formulación del problema de ML (núcleo del diseño)

### Construcción del set de entrenamiento
Para cada día histórico `D` y cada **hora de decisión** `H` ∈ {6, 7, …, 16}
(hora local Panamá), se genera **una fila** usando **solo lo conocible hasta H**:

**Features:**
- *Calendario:* día-del-año (seno/coseno), mes.
- *Hora de decisión H:* cuánto del día ha transcurrido.
- *Intradía hasta H* (de Open-Meteo): máximo-hasta-ahora, temp actual en H,
  temps de horas previas (H-1, H-2, H-3), tasa de subida reciente, humedad
  relativa, nubosidad.
- *Forecast del día* (de Open-Meteo): máxima pronosticada para hoy.
  Feature **nullable**: para días históricos sin forecast archivado queda NaN;
  LightGBM maneja faltantes nativamente.

**Target:**
- El **pico real** de ese día `D` según Wunderground MPMG (`temp_max_c`).

> **Sin fuga de datos (leakage):** los features intradía solo usan datos
> con timestamp ≤ H. Nunca se usa el máximo final del día de Open-Meteo como
> feature, porque en producción aún no se conoce a esa hora.

### Modelo
- **LightGBM con objetivo `quantile`**, tres modelos: p10, p50, p90.
- **p50** = pico estimado (punto). **[p10, p90]** = banda de confianza.
- La banda se estrecha de forma natural a media tarde: cuando el
  máximo-hasta-ahora ya casi alcanzó el pico, la incertidumbre cae.

### Métrica de evaluación
- Error absoluto del p50 vs pico real, **desglosado por hora de decisión H**,
  para visualizar cómo mejora la certeza durante el día.
- Cobertura de la banda (¿el pico real cae dentro de [p10, p90] ~80% de las veces?).

## 5. Arquitectura de ejecución

Se separa el **entrenamiento pesado** (1×/día) de la **inferencia ligera** (cada hora).

### `train.yml` — nocturno (1×/día, ~1am Panamá = `0 6 * * *` UTC)
1. Backfill incremental: añade los días nuevos al histórico horario y a las
   observaciones de Wunderground.
2. Reensambla el set de entrenamiento y reentrena los 3 modelos de cuantiles.
3. Guarda `models/peak_model.txt` (+ métricas) y hace commit.

### `hourly.yml` — cada hora diurna (`0 11-21 * * *` UTC = 6am–4pm Panamá, 11 corridas/día)
1. Carga el modelo entrenado.
2. Baja el intradía de hoy (Open-Meteo) + el forecast del día.
3. Construye la fila de features para la hora actual y predice p10/p50/p90.
4. Registra la predicción en `predictions.csv`.
5. Si un día previo ya cerró, evalúa el pico predicho vs el real (Wunderground)
   y actualiza `evaluation.csv`.
6. Exporta `docs/data.json` y despliega el dashboard (GitHub Pages).

### `backfill.yml` — manual (una vez)
Carga el histórico horario de Open-Meteo + los picos diarios de Wunderground
desde 2020-01-01.

> Nota: GitHub Actions ejecuta crons en UTC; Panamá es UTC-5 fijo (sin horario
> de verano), por lo que las franjas son estables todo el año.

## 6. Datos (`data/`)

| Archivo | Contenido | Estado |
|---------|-----------|--------|
| `observations.csv` | Pico diario real (Wunderground MPMG): `fecha, temp_max_c` | Se conserva |
| `hourly_history.csv` | Histórico horario Open-Meteo (base de entrenamiento) | Nuevo |
| `predictions.csv` | Por corrida: `run_timestamp, fecha_objetivo, hora_decision, pico_pred, p10, p90, modelo_version` | Reestructurado |
| `evaluation.csv` | Error del pico predicho vs real, por hora de decisión | Reestructurado |
| `models/peak_model.txt` | Modelo(s) entrenado(s), versionado(s) | Nuevo |

## 7. Código (`src/`)

| Módulo | Responsabilidad |
|--------|-----------------|
| `sources/openmeteo.py` | Archivo histórico, intradía de hoy, forecast del día |
| `sources/wunderground.py` | Scraper existente (pico diario real); se mueve aquí |
| `features.py` | Construye una fila de features dada la data cruda hasta la hora H |
| `dataset.py` | Ensambla la tabla de entrenamiento (día × hora de decisión) |
| `model.py` | Entrena/predice cuantiles, tras la interfaz `ajustar/predecir` (intercambiable, como hoy) |
| `train.py` | Orquesta el reentrenamiento nocturno y guarda el modelo + métricas |
| `predict.py` | Corrida horaria: carga modelo, predice, registra, evalúa, exporta |
| `backfill.py` | Reescrito: carga histórico de ambas fuentes |
| `export.py` | Construye el payload del dashboard |
| `storage.py` | Lectura/escritura de los CSV (adaptado a los nuevos esquemas) |
| `config.py` | Coordenadas, zona horaria, horas de decisión, rutas, versión del modelo |

**Principio de diseño (igual que hoy):** `model.py` expone `ajustar/predecir`
detrás de una interfaz estable, de modo que el algoritmo (LightGBM) sea
intercambiable sin tocar el pipeline.

## 8. Dashboard (`docs/`)

- **Número grande:** pico estimado de hoy (p50) + banda [p10, p90].
- **Curva de convergencia:** cómo evolucionó la predicción a lo largo de las
  horas de decisión de hoy (debe estrecharse y acercarse al real).
- **Pico real:** una vez cerrado el día.
- **Precisión reciente:** error medio por hora de decisión (muestra que predecir
  más tarde en el día es más certero).

## 9. Dependencias nuevas

- `lightgbm` (modelo).
- `requests` (ya presente) para Open-Meteo.
- Se mantienen `pandas`, `beautifulsoup4`, `lxml`, `playwright` (scraper Wunderground).

## 10. Fuera de alcance (YAGNI)

- Pronóstico a varios días (se retira; el foco es solo HOY).
- Deep learning / LSTM (Gradient Boosting es suficiente para este volumen tabular).
- Múltiples estaciones (solo MPMG).
- Reentrenamiento en cada corrida horaria (el entrenamiento es nocturno).

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Forecast histórico de Open-Meteo no disponible antes de ~2022 | Feature nullable; LightGBM tolera NaN |
| Diferencia sistemática Open-Meteo vs estación MPMG | El modelo aprende ese sesgo; el target siempre es MPMG |
| apiKey de Wunderground se rompe | Respaldo Playwright existente; el histórico horario (entrenamiento) no depende de Wunderground |
| Límite de uso no comercial de Open-Meteo | Volumen bajo (1 punto, 11 corridas/día); backfill en bloque puntual |
