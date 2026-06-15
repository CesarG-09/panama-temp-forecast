# Diseño — panama-temp-forecast

**Fecha:** 2026-06-14
**Autor:** César (con Claude Code)
**Estado:** Aprobado para planificación

## 1. Propósito

Sistema automático que cada día:

1. **Recolecta** la temperatura máxima diaria observada en la Ciudad de Panamá
   (estación **MPMG – Marcos A. Gelabert / Albrook**), desde **2020-01-01**.
2. **Re-ajusta** un modelo de predicción con todo el histórico disponible.
3. **Predice** la temperatura máxima de los **próximos 7 días**.
4. Al cerrar cada día, **compara** su predicción contra el valor observado y
   registra **acierto/fallo** para retroalimentar el modelo.
5. **Publica** histórico, predicciones y desempeño en un **dashboard web**.

La predicción es **propia del modelo**; el histórico de Wunderground se usa solo
para entrenar y para verificar el acierto al cierre del día. No se depende del
pronóstico de Wunderground.

## 2. Decisiones (tomadas en brainstorming)

| Decisión | Elección |
|---|---|
| Ejecución del trabajo diario | **GitHub Actions** (cron diario, en la nube) |
| Sofisticación del modelo | **Simple primero**, arquitectura intercambiable |
| Salida / visualización | **Dashboard web en GitHub Pages** |
| Estrategia de scraping | **API interna (api.weather.com) primero; Playwright de respaldo** |
| Visibilidad del repo | **Público** (Pages gratis) |
| Lenguaje | **Python 3.12** |
| Horizonte de predicción | **7 días** (configurable) |
| Umbral de "acierto" | **|error| ≤ 1.5 °C** (configurable) |
| Estación | **MPMG** (Marcos A. Gelabert / Albrook, Ciudad de Panamá) |
| Unidades | **°C** |

## 3. Stack

- Python 3.12
- `requests` — llamadas a la API interna de Wunderground/Weather.com
- `playwright` — respaldo de scraping con navegador headless
- `pandas` — manejo de series de datos
- Modelo estadístico propio (sin dependencias pesadas en v1)
- **GitHub Actions** — orquestación (cron + workflow_dispatch)
- **GitHub Pages** — dashboard estático con **Chart.js**

## 4. Arquitectura y componentes

Cada componente tiene un propósito único y una interfaz clara, para poder
entenderse y probarse de forma aislada.

```
panama-temp-forecast/
├─ .github/workflows/
│   ├─ daily.yml          # cron diario: pipeline completo + commit + deploy Pages
│   └─ backfill.yml       # workflow_dispatch: carga inicial del histórico
├─ src/
│   ├─ scraper.py         # obtención de datos (API interna + respaldo Playwright)
│   ├─ model.py           # modelo de predicción (interfaz ajustar/predecir)
│   ├─ evaluate.py        # comparación predicción vs observado, aciertos
│   ├─ pipeline.py        # orquesta: recolectar → evaluar → ajustar → predecir
│   └─ export.py          # genera docs/data.json para el dashboard
├─ data/
│   ├─ observations.csv
│   ├─ predictions.csv
│   └─ evaluation.csv
├─ docs/                  # GitHub Pages
│   ├─ index.html
│   ├─ app.js
│   └─ data.json
├─ tests/
├─ requirements.txt
└─ README.md
```

### 4.1 scraper.py
- **Qué hace:** dada una fecha o rango, devuelve `[(fecha, temp_max_c), ...]`.
- **Cómo:** primero la API interna JSON de `api.weather.com` que usa la web de
  Wunderground (endpoint de observaciones históricas por estación). Si falla
  (cambio de clave/endpoint, bloqueo), cae a Playwright leyendo la tabla
  renderizada de `https://www.wunderground.com/history/daily/pa/panama-city/MPMG`.
- **Depende de:** red. Se aísla del resto para poder testear el parseo con
  fixtures (JSON/HTML guardados) sin red.

### 4.2 model.py
- **Interfaz:** `Modelo.ajustar(historico: DataFrame)` y
  `Modelo.predecir(fechas: list[date]) -> list[float]`.
- **v1 (línea base climatológica + persistencia + corrección de sesgo):**
  - Media del máximo para ese día-del-año (ventana ±7 días sobre todos los
    años) → estacionalidad (leve en clima tropical).
  - Ajuste por anomalía reciente (los últimos días vs lo normal).
  - **Corrección de sesgo:** desplaza la predicción según el error medio
    reciente registrado en `evaluation.csv` → lazo de retroalimentación real.
- **Intercambiable:** sustituir por scikit-learn / series temporales sin tocar
  el resto del sistema, respetando la misma interfaz. Cada predicción se sella
  con `modelo_version`.

### 4.3 evaluate.py
- **Qué hace:** para cada predicción cuyo `fecha_objetivo` ya tiene observación,
  calcula `error_c = pred_c - real_c` y `acierto = |error_c| <= 1.5`.
  Escribe/actualiza `evaluation.csv`. Provee también métricas agregadas
  (MAE, % aciertos, tendencia del error) para el export.

### 4.4 pipeline.py
- **Orquesta el flujo diario** (sección 5). Punto de entrada del workflow.

### 4.5 export.py
- Genera `docs/data.json` con: histórico, predicciones vigentes y métricas de
  desempeño, listo para que el dashboard lo consuma.

## 5. Flujo diario (daily.yml)

A hora fija (p.ej. 12:00 UTC):

1. **Recolectar** — pedir los días nuevos observados desde la última corrida;
   append a `observations.csv`. (API interna → respaldo Playwright.)
2. **Evaluar** — para predicciones pasadas con día objetivo ya observado:
   calcular error y marcar acierto (≤ 1.5 °C). Guardar en `evaluation.csv`.
3. **Ajustar y predecir** — re-ajustar el modelo con todo el histórico +
   corrección de sesgo; predecir el máximo de los próximos 7 días →
   `predictions.csv`.
4. **Publicar** — `export.py` regenera `docs/data.json`; commit de
   CSV/JSON al repo y deploy de GitHub Pages.

Resultado: la predicción cambia sola cada día, sin depender de la PC del usuario,
y el historial de git muestra la evolución de cada predicción.

## 6. Datos

### 6.1 Backfill inicial (backfill.yml — una sola vez)
Descarga el histórico desde **2020-01-01** hasta hoy por bloques (mensuales) y
rellena `observations.csv`. Se ejecuta manualmente (`workflow_dispatch`) al
arrancar el proyecto.

### 6.2 Esquemas (CSV, amigables con git-diff)
- `observations.csv` → `fecha, temp_max_c`
- `predictions.csv` → `fecha_prediccion, fecha_objetivo, temp_max_pred_c, modelo_version`
- `evaluation.csv` → `fecha_objetivo, pred_c, real_c, error_c, acierto`

Guardar la **fecha en que se hizo** cada predicción evita usar datos futuros
("hacer trampa") y permite una auditoría honesta del desempeño.

## 7. Dashboard (GitHub Pages, docs/)

Página estática con Chart.js que lee `data.json`:
- Gráfica del histórico de máximas + predicciones de los próximos 7 días.
- Panel de desempeño: % aciertos, MAE, tendencia del error en el tiempo.
- Tabla de últimas predicciones con su veredicto (✅/❌) al cerrar el día.

## 8. Manejo de errores

- **Scraping:** reintentos con backoff en la API; si agota, cae a Playwright;
  si ambos fallan, el workflow falla de forma visible (sin escribir datos
  parciales corruptos) y se notifica vía estado del Action.
- **Días faltantes:** el sistema tolera huecos en `observations.csv`; el modelo
  usa los datos disponibles y los huecos quedan registrados.
- **Idempotencia:** re-correr un día no duplica filas (clave por fecha).

## 9. Testing

- **TDD** para la lógica pura: parseo de la respuesta de la API (fixtures JSON),
  evaluación de aciertos, y el modelo (entradas fijas → salidas esperadas).
- El scraping real (red) se prueba aparte, fuera del CI determinista.

## 10. Fuera de alcance (YAGNI por ahora)

- Modelos de ML pesados o series temporales dedicadas (la interfaz queda lista
  para añadirlos después).
- Múltiples estaciones/ciudades.
- Notificaciones (correo/Telegram) — posible extensión futura.
- Predicción de otras variables (lluvia, humedad).
