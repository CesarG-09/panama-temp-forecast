# Tabla histórica: hora de predicción y hora del pico

**Fecha:** 2026-06-30
**Estado:** Aprobado (brainstorming) — pendiente plan de implementación
**Alcance:** Añadir a la tabla histórica del dashboard la hora en que el modelo
fijó su predicción, la hora a la que ocurrió el pico real, y un indicador
"¿antes?". **No** se toca el modelo, los features, el entrenamiento ni los
workflows.

## 1. Objetivo

Saber, por día, **si la predicción se hizo antes de que ocurriera el pico**.
Para eso, la tabla histórica gana tres columnas: **Hora pred.** (cuándo el modelo
fijó su valor), **Hora pico** (cuándo ocurrió el pico real) y **¿Antes?**
(✓ si Hora pred. < Hora pico).

## 2. Decisiones (con justificación)

| Tema | Decisión | Porqué |
|---|---|---|
| "Hora de predicción" | La **primera** hora de decisión del día en que `trunc(pico_pred)` ya era igual a la predicción final (truncada) | Responde "¿cuándo lo supo el modelo?". La final se hace ~16h (después del pico), así que no sirve para esto. |
| "Hora del pico real" | Hora del máximo en las **observaciones horarias de la estación** (weather.com), misma fuente que el "Pico Real" | Exacto y consistente con el valor mostrado. |
| Obtención de la hora del pico | **Cache `data/peak_hours.csv`**, llenado por `predict.py` con **una sola llamada por rango** a `historical.json` para los días faltantes | Evita re-consultar cada hora; un día cacheado no se vuelve a pedir. `export` sigue puro (sin red). |
| Columna "¿Antes?" | Se incluye (✓/✗) | Es la intención directa del usuario. |
| Formato de hora | `HH:00` (p. ej. `13:00`) | Pedido del usuario; consistente con el resto del dashboard. |
| Persistencia del cache | `hourly.yml` ya hace `git add data/` | El cache se commitea solo; **sin tocar workflows**. |

## 3. Datos y cálculo

### 3.1 Hora de predicción (pura, en export)
Desde `predictions.csv` (cols `fecha_objetivo, hora_decision, pico_pred, …`):
para cada día, `prediccion = trunc(pico_pred de la hora de decisión máxima)`;
`hora_prediccion = min(hora_decision)` entre las filas del día con
`trunc(pico_pred) == prediccion`. Siempre está definida (la fila final coincide
consigo misma).

### 3.2 Hora del pico real (cache + fetch por rango)
- `wunderground.parse_horas_pico(payload) -> dict[str, int]`: agrupa las
  observaciones por día (hora local de Panamá) y devuelve, por día, la **hora
  local del máximo de `temp`** (en empate, la más temprana).
- `wunderground.fetch_horas_pico(desde, hasta) -> dict[str, int]`: **una** llamada
  a `historical.json?startDate=desde&endDate=hasta&units=m` y parseo con
  `parse_horas_pico`.
- `data/peak_hours.csv` (cache nuevo): columnas `fecha, hora_pico` (entero 0–23).
- `predict.py`: antes de exportar, determina los días observados recientes
  (últimos ~25) sin `hora_pico` en cache; si hay faltantes, hace **una** llamada
  de rango `[min(faltantes), max(faltantes)]`, y hace upsert de los que devuelva.
  Todo en `try/except`: si falla, el cache queda parcial y se reintenta la
  próxima corrida. La **primera corrida** rellena los ~20 días de la tabla; luego
  ~1/día.

### 3.3 ¿Antes? (pura, en export)
`antes = (hora_prediccion < hora_pico)` cuando `hora_pico` existe; `None` si la
hora del pico no está en cache.

## 4. Contratos de datos

### 4.1 `data/peak_hours.csv` (nuevo)
```
fecha,hora_pico
2026-06-25,13
2026-06-24,14
```

### 4.2 `data.json` → cada item de `tabla_historica` (gana 3 llaves)
```json
{
  "fecha": "2026-06-25",
  "prediccion": 32,
  "real": 32,
  "hora_prediccion": 9,
  "hora_pico": 13,
  "antes": true,
  "se_cumplio": true,
  "tasa_error_pct": 0.0,
  "diferencia": 0
}
```
- `hora_prediccion`: entero 0–23 (siempre presente).
- `hora_pico`: entero 0–23 **o `null`** (si no está en cache).
- `antes`: bool **o `null`** (null si `hora_pico` es null).

### 4.3 Firmas
- `construir_tabla_historica(predicciones, observaciones, horas_pico=None, n_dias=20)`
  — `horas_pico` es `dict[str, int]` (`fecha -> hora`); `None` se trata como `{}`.
- `construir_payload(..., horas_pico=None)` — pasa `horas_pico` a la tabla.

## 5. UI

Tabla en la zona *Desempeño*, agrupando cada valor con su hora:

```
Día   | Predicción | Hora pred. | Pico Real | Hora pico | ¿Antes? | Se cumplió | Tasa de error | Diferencia
06-25 |   32°C     |   09:00    |   32°C    |   13:00   |    ✓    |   ✓ Sí     |    0.0%       |   0°C
06-21 |   31°C     |   08:00    |   32°C    |   14:00   |    ✓    |   ✗ No     |    3.1%       |  -1°C
```

- `Hora pred.` = `${hora_prediccion}:00`. `Hora pico` = `${hora_pico}:00` o `—`.
- `¿Antes?` = ✓ (verde) si `antes` es true, ✗ (rojo) si false, `—` si null.
- La tabla va dentro de un contenedor con `overflow-x: auto` para que en móvil
  haga scroll horizontal (son 9 columnas).

## 6. Componentes / cambios por archivo

- `src/sources/wunderground.py` — `parse_horas_pico` + `fetch_horas_pico` (una
  llamada de rango).
- `src/config.py` — `ruta_peak_hours()` → `data/peak_hours.csv`.
- `src/storage.py` — `read_peak_hours()` / `upsert_peak_hours(filas)` (dedup por
  `fecha`, keep last, ordenado).
- `src/predict.py` — rellenar el cache (faltantes de los últimos ~25 días) y pasar
  `horas_pico` a `construir_payload`.
- `src/export.py` — `construir_tabla_historica` calcula `hora_prediccion`,
  `hora_pico`, `antes`; `construir_payload` recibe y pasa `horas_pico`.
- `docs/index.html` — 3 columnas nuevas + contenedor con scroll horizontal.
- `docs/app.js` — `renderTablaHistorica` pinta las celdas nuevas.
- Tests en `tests/test_export.py` y `tests/test_wunderground.py`.

## 7. Manejo de errores

| Situación | Comportamiento |
|---|---|
| `fetch_horas_pico` falla (red/clave) | El cache queda como estaba; se reintenta la próxima corrida; celdas "—" |
| Día observado sin datos horarios de la estación | No aparece en el parse → no se cachea → "—" |
| `data.json` viejo sin los campos nuevos | `hora_pico`/`antes` ausentes → celdas "—" |
| `horas_pico` no provisto (tests/llamadas directas) | `hora_pico`=null, `antes`=null; `hora_prediccion` sí se calcula |

## 8. Testing

- **export:** `hora_prediccion` (primera hora con trunc igual al final);
  `antes` (true / false / null cuando falta `hora_pico`); actualizar los tests
  existentes de la tabla para las 3 llaves nuevas.
- **wunderground:** `parse_horas_pico` con un payload de muestra (hora del máximo
  por día, empate → la más temprana), siguiendo el patrón de `test_wunderground.py`.
- **JS:** verificación visual en Pages.

## 9. Fuera de alcance

- Cambios al modelo, features, entrenamiento o workflows.
- Persistir la hora del pico dentro de `observations.csv` (se usa un cache aparte
  para no cambiar ese esquema).
- Backfill dedicado: el cache se llena solo (lazy) en la primera corrida.
