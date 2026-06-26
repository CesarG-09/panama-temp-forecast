# % de acierto del pico + tabla histórica de predicciones

**Fecha:** 2026-06-26
**Estado:** Aprobado (brainstorming) — pendiente plan de implementación
**Alcance:** Dos adiciones a la visualización del dashboard, derivadas de datos
ya existentes (`evaluation.csv` / `predictions.csv` / `observations.csv`). **No**
se toca el modelo predictivo, los workflows ni los CSV.

Se construye sobre el dashboard reestructurado (zonas *En vivo* / *Desempeño*) ya
en `main`.

## 1. Objetivo

1. **% de acierto junto al pico:** en cada actualización horaria, mostrar junto al
   pico previsto una frase tipo *"≈80% probable que este sea el pico"*, basada en
   qué tan seguido aciertan históricamente las predicciones hechas a esa hora.
2. **Tabla histórica:** una tabla de las **últimas 20 predicciones** (una por día)
   con las columnas: Día · Predicción · Pico Real · Se cumplió (sí/no) · Tasa de
   error · Diferencia.

## 2. Decisiones (con justificación)

| Tema | Decisión | Porqué |
|---|---|---|
| Significado del % | **Acierto histórico por hora de decisión**: fracción de días pasados en que la predicción hecha *a esa hora* cayó dentro del umbral | Es literalmente una tasa de acierto, honesta y derivada de la data real; sube conforme avanza el día. |
| Tolerancia de acierto | **±1.5°C** (`config.UMBRAL_ACIERTO_C`) | Consistente con la tasa de acierto que ya muestra la zona Desempeño. |
| Filas de la tabla | **1 fila por día**, últimos 20 días, usando la **predicción final** del día (hora de decisión máxima) | Registro 'definitivo' de qué dijo el modelo vs qué pasó; legible. |
| Columna "Diferencia" | `predicción − real` en °C, **con signo** | Muestra si el modelo sobre- o subestima. |
| Columna "Tasa de error" | error relativo `% = |predicción − real| / real × 100` | Distinta y complementaria a Diferencia. |
| Columna extra "Día" | **Se añade** como primera columna | Sin fecha, 20 filas anónimas confunden. |
| Ubicación de la tabla | En la zona *Desempeño*, **debajo de "Predicciones pasadas vs. real"** | Mismo tema. |
| Pocos datos | Mostrar el respaldo `· histórico de N días`; si `N < 5` añadir `(pocos datos aún)`; si `N = 0` ocultar la frase | `evaluation.csv` arranca ~2026-06-17 (~7–9 días por hora); transparencia en vez de fingir precisión. |

## 3. Feature 1 — % de acierto junto al pico

### 3.1 Cálculo (backend)

Desde `evaluation.csv` (cols `fecha_objetivo, hora_decision, pico_pred,
pico_real, error_c`), agrupando por `hora_decision`:

- `pct(H) = media( |error_c| <= UMBRAL_ACIERTO_C )` sobre los días con esa hora.
- `n(H) = número de días` evaluados a esa hora.

Para la predicción más reciente de hoy (la que define `pico_hoy`, con su
`hora_decision = H*`), se adjunta el valor de `H*`:

- `pico_hoy.prob_acierto = round(pct(H*) * 100)` (entero 0–100) **o `null`** si
  `n(H*) == 0`.
- `pico_hoy.prob_n = n(H*)` (entero) **o `null`** si `n(H*) == 0`.

> Esto reutiliza la misma agregación que ya produce `error_por_hora`.

### 3.2 Presentación (frontend)

En la **tarjeta del PICO**, una línea nueva entre la banda y el meta:

- `n ≥ 5`: `≈{prob_acierto}% probable que este sea el pico · histórico de {prob_n} días`
- `1 ≤ n < 5`: igual + ` (pocos datos aún)`
- `n = 0` / `prob_acierto == null`: la línea **no se muestra**.

## 4. Feature 2 — Tabla histórica de las últimas 20 predicciones

### 4.1 Builder (backend)

`construir_tabla_historica(predicciones, observaciones, n_dias=20) -> list[dict]`

- Para cada día con pico real: la **predicción final** = fila con `hora_decision`
  máxima en `predictions.csv` de ese día.
- `prediccion = round(final.pico_pred, 1)`; `real = round(temp_max_c, 1)`.
- `diferencia = round(prediccion - real, 1)` (con signo).
- `tasa_error_pct = round(abs(prediccion - real) / real * 100, 1)`.
- `se_cumplio = abs(prediccion - real) <= UMBRAL_ACIERTO_C` (bool).
- Orden **descendente por fecha** (más reciente primero); devuelve las primeras
  `n_dias`. Sin datos → `[]`.

Nuevo campo en `data.json`: `tabla_historica`, cada item:

```json
{
  "fecha": "2026-06-24",
  "prediccion": 33.1,
  "real": 33.0,
  "se_cumplio": true,
  "tasa_error_pct": 0.3,
  "diferencia": 0.1
}
```

`real` siempre > 0 (temperaturas ~26–34°C), así que la división de `tasa_error_pct`
es segura.

### 4.2 Presentación (frontend)

Tabla HTML en la zona *Desempeño*, debajo del gráfico "pasadas vs real":

```
Registro de las últimas 20 predicciones
Día | Predicción | Pico Real | Se cumplió | Tasa de error | Diferencia
06-24 | 33.1°C | 33.0°C | ✓ Sí | 0.3% | +0.1°C
06-23 | 30.6°C | 30.0°C | ✓ Sí | 2.0% | +0.6°C
...
```

- `Día` = `fecha` recortada a `MM-DD`.
- `Predicción` / `Pico Real` con un decimal y `°C`.
- `Se cumplió` = `Sí` (verde) / `No` (rojo).
- `Tasa de error` = `{tasa_error_pct}%`.
- `Diferencia` = `{diferencia}°C` con signo explícito (`+` cuando ≥ 0).
- Si `tabla_historica` está vacío → nota *"Se llenará conforme se acumulen días."*

## 5. Cambios por archivo

**Backend (`src/export.py`, no toca el modelo):**
- Calcular `pct`/`n` por `hora_decision` (junto a `error_por_hora`) y adjuntar
  `prob_acierto`/`prob_n` a `pico_hoy`.
- Builder nuevo `construir_tabla_historica`; `construir_payload` agrega la llave
  `tabla_historica`.
- `tests/test_export.py`: tests del acierto-por-hora en `pico_hoy` y de
  `construir_tabla_historica`.

**Frontend (`docs/`):**
- `index.html`: en la tarjeta del pico, un contenedor `#pico-prob`; en *Desempeño*,
  la tabla (`#tabla-historica` con `thead` + `tbody#tabla-historica-body`) y su
  nota vacía `#tabla-nota`; estilos de tabla.
- `app.js`: `pintarPico` setea la línea de probabilidad; función nueva
  `renderTablaHistorica(arr)` que pinta el `tbody` (o muestra la nota). Se llama
  desde `refrescarDatos` (se actualiza con el resto de la zona Desempeño cada 30 min).

## 6. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Sin historial para la hora actual (`n=0`) | La línea de probabilidad no se muestra |
| `prob_n` entre 1 y 4 | Se muestra con `(pocos datos aún)` |
| `tabla_historica` vacío (arranque) | Se muestra la nota *"se llenará…"* |
| `data.json` viejo sin los campos nuevos | `pico_hoy.prob_acierto` ausente → sin línea; `tabla_historica` ausente → `|| []` → nota |

## 7. Testing

- **Python (pytest):**
  - Acierto-por-hora: con `evaluation` de casos conocidos, verificar
    `pico_hoy.prob_acierto` y `prob_n` para la hora de la última predicción, y
    `null` cuando esa hora no tiene historial.
  - `construir_tabla_historica`: `se_cumplio` (bool en el borde de 1.5),
    `tasa_error_pct` (% relativo), `diferencia` (con signo), orden descendente,
    tope de 20, y `[]` en vacío.
- **JS:** verificación visual en Pages (sin infra de tests nueva).

## 8. Fuera de alcance

- Cambios al modelo, features, entrenamiento o workflows.
- Calibración probabilística avanzada (p. ej. probabilidad de que el pico ya no se
  supere): el % es una tasa de acierto histórica, no una probabilidad calibrada.
- Hacer la tabla ordenable/filtrable o paginada.
