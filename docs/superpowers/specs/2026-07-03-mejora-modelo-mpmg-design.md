# Mejora del modelo de pico: datos MPMG intradía, backtest y calibración

**Fecha:** 2026-07-03
**Estado:** aprobado (el usuario delegó las decisiones de diseño)

## Problema

El modelo `gbm-q-v1` casi no usa la información intradía. La importancia (gain) del
regresor p50 se concentra en `forecast_max` (65%) y estacionalidad (`doy_sin`/`doy_cos`/
`mes`, 29%); todas las features intradía juntas aportan ~2%. En consecuencia:

1. La predicción apenas cambia entre las 6am y las 4pm, aunque a media tarde el pico
   real ya ocurrió y está registrado en la estación MPMG (errores de hasta ±1.4 °C a
   las 15–16h, cuando debería ser trivial).
2. El modelo hereda el sesgo del pronóstico de Open-Meteo (-1.05 °C promedio en los
   últimos 30 días), lo que produjo 6 días consecutivos de subestimación (~-1 °C).
3. El intervalo p10–p90 cubre el valor real solo el 45.7% de las veces (objetivo: 80%).

**Causa raíz:** desajuste de dominios. Las features intradía (entrenamiento y
predicción) salen de la celda de Open-Meteo/ERA5, con sesgo frío de 2–3 °C y una
dinámica distinta a la de la estación; el target es el pico real de MPMG. Como la
curva de Open-Meteo no sigue bien a la estación, LightGBM aprende a ignorarla.

## Objetivo

- Reducir el MAE (hoy 0.93 °C global), sobre todo en horas de la tarde, donde el error
  debería tender a cero.
- Eliminar la incoherencia de predecir por debajo del máximo ya observado.
- Llevar la cobertura del intervalo p10–p90 a ~80%.
- Poder medir cualquier cambio del modelo con un backtest reproducible antes de
  desplegarlo.

## Alternativas consideradas

1. **Corrección de sesgo post-hoc (rolling)** — restar el error medio de los últimos
   5 días. **Descartada:** se probó sobre `evaluation.csv` y empeora (MAE 0.96 vs
   0.93); el sesgo cambia de signo entre semanas.
2. **Reentrenar el intradía desde la Historical Forecast API** (arreglar el skew
   ERA5-vs-forecast-API sin tocar MPMG). Ataca el skew de fuente pero no el de
   dominio (celda vs estación), que es el dominante. **Pospuesta** como trabajo
   futuro; no bloquea esta fase.
3. **Features intradía de la estación real MPMG + regla dura + backtest +
   calibración conformal.** **Elegida:** ataca la causa raíz con datos que ya
   consumimos (la API de Weather.com que alimenta el dashboard) y hace medible
   cualquier mejora futura.

## Diseño

Tres fases independientes, desplegables por separado. La versión del modelo pasa a
`gbm-q-v2` cuando entra la Fase B (cambia el contrato de features).

### Fase A — Regla dura: el pico no puede ser menor que lo ya observado

En `predict.correr` la curva intradía de MPMG se descarga **antes** de predecir (hoy
se descarga después, solo para el dashboard). Si la curva está disponible:

```
piso = max(temp_c de la curva hasta la hora actual)
p10, p50, p90 = max(p10, piso), max(p50, piso), max(p90, piso)
```

- Si la API de Wunderground falla (curva `None`), la regla no se aplica y todo sigue
  como hoy (degradación suave, mismo patrón de respaldo actual).
- La curva descargada se reutiliza para el dashboard: **no hay llamadas extra** a la API.
- El piso se aplica después del redondeo/monotonía de `ModeloPico.predecir`, en
  `predict.py` (el modelo no conoce la regla; es una restricción del dominio).

### Fase B — Features intradía de MPMG

**Nueva fuente de datos:** `data/mpmg_hourly.csv` con columnas `fecha,hora,temp_c`
(temperatura máxima por hora local de la estación MPMG, igual que la tabla horaria de
wunderground.com).

- **Fetch por rango:** nueva función `wunderground.fetch_horario_rango(desde, hasta)`
  que reutiliza el endpoint `observations/historical.json` (ya acepta rangos; ver
  `fetch_horas_pico`) y un parser `parse_horario_rango` que agrupa por (fecha, hora)
  con el máximo por hora. El backfill pide mes a mes, como `_corregir_con_wunderground`.
- **Backfill:** `backfill.correr` gana un paso 3 que llena `mpmg_hourly.csv` desde
  `FECHA_INICIO` (~78 llamadas mensuales). Tolerante a fallos por mes (mismo patrón
  try/except con aviso) y re-ejecutable (upsert por `fecha,hora`).
- **Actualización diaria:** `backfill.actualizar_reciente` refresca también los
  últimos 7 días de `mpmg_hourly.csv` (una sola llamada de rango).
- **Features nuevas** (al final de `FEATURE_COLS`):
  - `temp_actual_mpmg`: temperatura de la estación en la hora de decisión (o la
    última hora disponible ≤ hora de decisión, porque la estación puede atrasarse
    unos minutos).
  - `max_hasta_ahora_mpmg`: máximo de la estación hasta la hora de decisión.
- `features.construir_fila` recibe un parámetro opcional `mpmg_intradia`
  (lista/DataFrame de `{hora, temp_c}` del día); si falta, ambas features quedan
  `None` → NaN, que LightGBM maneja de forma nativa. Así los días sin dato MPMG
  siguen siendo entrenables.
- `dataset.construir_set` recibe el horario MPMG y lo pasa por fecha;
  `train.correr` lo lee de storage; `predict.correr` lo construye desde la curva ya
  descargada (Fase A).
- `config.MODELO_VERSION = "gbm-q-v2"`.

**Nota de despliegue:** el modelo v2 se entrena con el workflow de train una vez
corrido el backfill de `mpmg_hourly.csv`. Mientras tanto el modelo v1 en producción
sigue funcionando: `construir_fila` solo añade claves y `_matriz` selecciona por
`FEATURE_COLS`, así que el orden de despliegue es backfill → train → predict.

### Fase C — Backtest temporal y calibración de cuantiles

**Backtest (`src/backtest.py`):** validación rolling-origin mensual.

- Para cada uno de los últimos `n_meses` (default 6): entrenar con todos los datos
  anteriores al mes M y predecir cada (día, hora de decisión) de M.
- Métricas por corrida y agregadas: MAE, sesgo, % acierto ≤ `UMBRAL_ACIERTO_C`,
  cobertura p10–p90 y ancho medio del intervalo; desglose por hora de decisión.
- CLI: `python -m src.backtest [n_meses]`, imprime la tabla. Sin efectos sobre
  `data/` ni `models/` (no escribe nada).
- Sirve como harness para comparar v1 vs v2 antes de desplegar.

**Calibración conformal (CQR simplificado):**

- En `train.correr`: separar como conjunto de calibración los últimos 45 días con
  target; entrenar con el resto; calcular el score de conformidad
  `E = max(p10 - y, y - p90)` sobre calibración y `q_hat = cuantil 0.8 de E`
  (ajuste de muestra finita `(1-α)(1+1/n)` con α=0.2). Después **re-entrenar con
  todos los datos** (mismos hiperparámetros) y guardar `q_hat` junto a los boosters.
- En `ModeloPico.predecir`: intervalo ajustado `[p10 - q_hat, p90 + q_hat]`; p50 no
  cambia. `q_hat` puede ser negativo (intervalo se encoge) — se admite, con el piso
  de monotonía p10 ≤ p50 ≤ p90 ya existente.
- **Formato del archivo de modelo:** el JSON gana una clave `"calibracion":
  {"q_hat": <float>}`. `ModeloPico.cargar` tolera su ausencia (q_hat = 0.0), así el
  modelo v1 en producción sigue cargando durante la transición.

## Manejo de errores

- API de Wunderground caída: Fase A no aplica el piso; Fase B deja las features MPMG
  en NaN (el modelo degrada al comportamiento actual); `actualizar_reciente` ya
  traga la excepción. Nada rompe.
- Meses sin cobertura en el backfill MPMG: quedan como huecos; el dataset los trata
  como NaN.
- Backtest con datos insuficientes en un mes: ese mes se omite con aviso.

## Pruebas

TDD con la suite existente (pytest, fixtures JSON en `tests/fixtures`):

- `test_wunderground`: parser de rango horario (agrupación por fecha+hora, máximo).
- `test_predict`: el piso se aplica cuando hay curva y no se aplica cuando es `None`;
  la curva se descarga una sola vez.
- `test_features` / `test_dataset`: features MPMG presentes, NaN cuando falta el dato,
  hora atrasada usa la última disponible.
- `test_model`: round-trip guardar/cargar con y sin `calibracion`; q_hat aplicado.
- `test_train`: split de calibración + refit final.
- `test_backtest`: métricas correctas sobre un dataset sintético pequeño.
- `test_storage` / `test_backfill`: upsert de `mpmg_hourly.csv`.

## Criterios de éxito

- Backtest v2 vs v1: MAE menor, especialmente a las 12–16h (esperado: ≪0.5 °C en la
  tarde); cobertura p10–p90 en 70–90%.
- En producción: ninguna predicción por debajo del máximo ya observado en MPMG.
- Suite de tests en verde; workflows de Actions sin cambios de contrato (solo el
  backfill tarda más la primera vez).

## Fuera de alcance (trabajo futuro)

- Unificar la fuente intradía de entrenamiento con la Historical Forecast API
  (skew ERA5 vs forecast API).
- Features adicionales (viento, precipitación, trayectoria horaria del forecast).
- Ajuste de hiperparámetros de LightGBM (el backtest de esta fase lo hace posible).
