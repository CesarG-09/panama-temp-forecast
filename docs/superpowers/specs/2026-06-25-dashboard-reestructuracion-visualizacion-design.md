# Reestructuración de la visualización del dashboard

**Fecha:** 2026-06-25
**Estado:** Aprobado (brainstorming) — pendiente plan de implementación
**Alcance:** Solo visualización y el plumbing de datos que la alimenta. **No** se
toca el modelo predictivo, los CSV de datos, ni los workflows de
predicción/entrenamiento.

## 1. Objetivo

Mejorar cómo se comparte la información en la página principal
(GitHub Pages) con cuatro piezas:

1. **Temperatura actual** de Ciudad de Panamá, estación **MPMG (Marcos A.
   Gelabert / Albrook)**, refrescada **cada 30 min**, tomada de la estación que
   publica Wunderground.
2. **Temperatura registrada hoy** (curva horaria del día en curso) de la misma
   estación.
3. **Predicciones de días anteriores vs. el valor real.**
4. **Evolución de la mejora del modelo** en el tiempo.

## 2. Decisiones (con justificación)

| Tema | Decisión | Porqué |
|---|---|---|
| Refresco de 30 min | **Híbrido**: el navegador llama directo a la API de weather.com cada 30 min; si falla, cae al `data.json` del backend | El "AHORA" queda vivo 24/7 e independiente del cron *best-effort* de GitHub. CORS verificado (`Access-Control-Allow-Origin: *`). El respaldo evita que la página se rompa. |
| Predicción de referencia | **Mañana (primera hora de decisión) y final (última)**, ambas vs. real | Ver de un vistazo cuánto gana el modelo al afinar durante el día. La de la mañana es el pronóstico honesto "a futuro". |
| Métrica de evolución | **Error en °C + tendencia (media móvil)** y **tasa de acierto %** (±1.5°C) | Dos lecturas complementarias: "¿cuánto se equivoca y baja?" y "¿a qué % le atina y sube?". |
| Layout | **Dos zonas: "En vivo" y "Desempeño"** | Separa los dos públicos: el curioso del clima y quien evalúa la calidad del modelo. |
| Precisión por hora de decisión (gráfico actual) | **Conservar como gráfico secundario** en Desempeño | Muestra el gradiente completo 6am→4pm que el par mañana/final no da. |
| Banda p10–p90 de la mañana en "pasadas vs real" | **Mostrarla tenue** | Permite ver si el real cae dentro de la banda. |

## 3. Arquitectura y flujo de datos

La misma API de weather.com
(`/v1/location/MPMG:9:PA/observations/historical.json?...&startDate=HOY`)
entrega en **una sola llamada** la temperatura actual (última observación del
día) y la curva horaria de hoy. Eso alimenta las piezas #1 y #2 en vivo desde el
navegador.

Dos fuentes con dos cadencias:

| Pieza | Fuente | Cadencia |
|---|---|---|
| Temp actual + curva de hoy (zona *En vivo*) | `api.weather.com` **directo desde el navegador** | cada **30 min** + al reenfocar la pestaña |
| Pico previsto + pasadas vs real + evolución (zona *Desempeño*) | `data.json` publicado por el backend | cuando corre el workflow (horario, 6am–4pm) |

Flujo al cargar y cada 30 min:

```
navegador
  ├─ fetch data.json  ──► pico previsto, pasadas vs real, evolución (siempre)
  │                       + temp_actual/curva de RESPALDO
  └─ fetch api.weather.com (hoy) ──► ¿ok? ─► AHORA + curva en vivo (pisa el respaldo)
                                     └ falla (CORS/red) ─► usa el respaldo de data.json
```

Notas:
- Las **predicciones** las calcula el modelo en el backend; no se recomputan en
  el navegador. Siguen viniendo de `data.json` (con su cache-busting `?v=` actual).
- **apiKey:** se usa la clave pública de los widgets de Wunderground
  (`e1f10a1e78da46f5b10a1e78da96f525`), ya visible en la web pública. Embeberla en
  el JS del cliente no expone nada nuevo.
- GitHub Pages sirve por HTTPS y `api.weather.com` también → sin *mixed content*.
- **America/Panama = UTC−5 fijo** (sin horario de verano): la conversión de
  `valid_time_gmt` (epoch UTC) a hora local es un simple offset de −5 h.

## 4. Estructura de la UI (dos zonas)

Una sola columna, estilo minimalista actual, con dos bloques encabezados.

### 4.1 Zona "En vivo"

**Hero — dos números grandes lado a lado:**

```
┌─────────────── EN VIVO ───────────────┐
│   AHORA            │   PICO PREVISTO   │
│   31.0°C           │   33.0°C          │
│   MPMG · 13:12     │   banda 32.2–33°  │
│   ↻ cada 30 min    │   estimado 14:00  │
└────────────────────┴───────────────────┘
```

- **AHORA** ← fetch en vivo (última observación de hoy). Sello discreto
  *"actualizado hace X min · ↻ 30 min"*.
- **PICO PREVISTO** ← `data.json.pico_hoy` (p50 + banda p10–p90 + hora de
  decisión). Es el techo del día, no la hora actual (se conserva la distinción
  que ya explica la página).
- Fuera de 6am–4pm (sin pico nuevo): AHORA sigue vivo; el lado del pico muestra
  el último o *"aún sin predicción para hoy"*.

**Curva de hoy:** temperatura observada hora a hora de hoy + banda del pico
previsto superpuesta. Cuando el fetch en vivo trae datos, la curva se extiende
sola cada 30 min sin esperar al workflow.

### 4.2 Zona "Desempeño"

**Predicciones pasadas vs real** (últimos ~30 días con pico real): 3 series —
**real** (sólida), **predicción de la mañana** (p50, línea, con banda p10–p90
tenue) y **predicción final** (p50, línea).

**Evolución del modelo** — dos mini-gráficos apilados:
- (a) **Error en °C + tendencia:** error absoluto por día (mañana y final) con
  media móvil de 7 días.
- (b) **Tasa de acierto %:** % de días dentro de ±1.5°C (umbral
  `config.UMBRAL_ACIERTO_C`) en ventana móvil de 7 días, para mañana y final.

**Precisión por hora de decisión** (secundario): el gráfico de barras actual
(MAE agregado 6am→4pm), al final de la zona.

> **Expectativa honesta:** `evaluation.csv` arranca el 2026-06-17 (~8 días al
> momento del spec). Los gráficos de evolución se verán cortos/planos al
> principio y cobran sentido conforme se acumulan semanas. Se construyen listos
> para crecer.

## 5. Contratos de datos

### 5.1 `docs/data.json` (cambios)

- **Se conservan:** `hoy`, `generado`, `temp_actual`, `pico_hoy`, `curva_hoy`,
  `convergencia_hoy`, `error_por_hora`.
- **Se elimina:** `observados_recientes` (su info —el pico real— ahora vive en
  `pasadas_vs_real`; el gráfico "Picos reales recientes" se retira).
- **Se agregan** dos llaves nuevas:

`pasadas_vs_real` — arreglo ascendente por fecha, últimos ~30 días con pico real:

```json
{
  "fecha": "2026-06-24",
  "real": 33.0,
  "manana_p50": 32.6,
  "manana_p10": 31.6,
  "manana_p90": 33.0,
  "final_p50": 33.1
}
```

`evolucion_modelo` — arreglo ascendente por fecha (todos los días con
evaluación):

```json
{
  "fecha": "2026-06-24",
  "err_manana": 0.4,
  "err_final": 0.1,
  "mae7_manana": 1.2,
  "mae7_final": 0.6,
  "acierto7_manana": 0.71,
  "acierto7_final": 0.86
}
```

- `manana` / `final` por día = fila con hora de decisión **mínima** / **máxima**
  en `predictions.csv` (o `evaluation.csv`) para esa fecha objetivo.
- `err_*` = `abs(error_c)` de ese día.
- `mae7_*` = media móvil de 7 días del error absoluto (mínimo 1 dato, de modo que
  esté definido desde el primer día).
- `acierto7_*` = fracción de días dentro de ±1.5°C en ventana móvil de 7 días
  (mínimo 1 dato). En la UI se muestra como porcentaje.

### 5.2 Respuesta de `api.weather.com` (consumida por el cliente)

`units=m` → `temp` ya viene en °C. Campos usados por observación:
`temp` (°C) y `valid_time_gmt` (epoch s, UTC).

- **AHORA** = observación de hoy con `valid_time_gmt` máximo →
  `{ temp_c, hora_local }`.
- **curva** = por hora local de hoy, el `temp` máximo de la hora.
- **hoy** = fecha local de Panamá (UTC−5) calculada en el cliente, **no**
  `data.json.hoy`, para seguir vivo aunque `data.json` esté viejo.

Esto replica la lógica ya probada en `src/sources/wunderground.py`
(`parse_actual`, `parse_curva_intradia`).

## 6. Cambios por archivo

**Backend (no toca el modelo):**
- `src/export.py` — dos builders nuevos: `construir_pasadas_vs_real(predicciones,
  observaciones)` y `construir_evolucion(evaluacion)`; `construir_payload` agrega
  las llaves `pasadas_vs_real` y `evolucion_modelo` y deja de emitir
  `observados_recientes`.
- `src/predict.py` — pasa los dos nuevos builders al payload. Sin cambios de
  lógica del modelo.

**Frontend (`docs/`):**
- `docs/live.js` (**nuevo**) — `fetchEnVivo()`: arma la fecha de hoy en Panamá
  (UTC−5), llama a `api.weather.com`, parsea AHORA y curva; agenda al cargar +
  `setInterval` 30 min + en `visibilitychange`. apiKey pública como constante.
  Todo en `try/catch`: nunca lanza.
- `docs/app.js` — render de las dos zonas; gráficos de "pasadas vs real" (3
  series + banda tenue de la mañana) y "evolución" (dos mini-gráficos), más el
  secundario de precisión por hora. Integra los datos en vivo de `live.js` cuando
  están disponibles, con respaldo a `data.json`.
- `docs/index.html` — estructura de dos zonas con encabezados *En vivo* /
  *Desempeño*, estilo minimalista actual.

## 7. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Fetch en vivo falla (red/límite) | Cae al `temp_actual`/`curva_hoy` de `data.json`; la página no se rompe |
| Sin `temp_actual` ni en vivo | AHORA se oculta con nota discreta |
| Última observación vieja (>~90 min) | AHORA atenuado: *"dato con retraso"* |
| Aún sin predicción hoy | Lado del pico: *"aún sin predicción para hoy"* |
| `pasadas`/`evolución` vacíos (arranque) | Mensaje: *"se llenará conforme se acumulen días"* |
| `data.json` viejo sin campos nuevos | Cada gráfico se salta si falta su campo (guardas) |

## 8. Testing y verificación

- **Python (pytest, ya configurado):** tests unitarios de
  `construir_pasadas_vs_real` y `construir_evolucion` — selección mañana/final,
  MAE y acierto móviles, y casos borde (día con una sola predicción →
  mañana=final; día sin pico real → excluido; primeros días con ventana <7).
- **JS:** sin infra de tests nueva (flujo sin Node local). El parser de `live.js`
  se mantiene pequeño y puro; se valida contra una respuesta real capturada de la
  API y luego en el deploy de Pages.
- **Verificación final:** en GitHub Pages tras el merge (sitio estático, sin
  build).

## 9. Riesgos

- **CORS / disponibilidad de la API desde el navegador:** mitigado — verificado
  hoy (`Access-Control-Allow-Origin: *`) y, ante cualquier fallo futuro, el
  respaldo de `data.json` mantiene la página funcional.
- **Pocos datos de evaluación al inicio:** los gráficos de evolución serán cortos
  hasta acumular semanas; es esperado y honesto en la UI.
- **Estación MPMG reporta cada ~30–60 min:** el refresco de 30 min está alineado
  con la cadencia real de la estación; se marca *"dato con retraso"* si la última
  observación es vieja.

## 10. Fuera de alcance

- Cambios al modelo, features, entrenamiento o backfill.
- Nuevos workflows o cambios de cadencia de los existentes.
- Un job de backend dedicado de 30 min para la temp actual (el respaldo actual
  horario basta; se reconsidera solo si el fetch en vivo resultara poco fiable).
