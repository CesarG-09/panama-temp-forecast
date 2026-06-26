# Reestructuración de la visualización del dashboard — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reestructurar el dashboard de GitHub Pages en dos zonas (En vivo / Desempeño), con la temperatura actual de MPMG refrescada cada 30 min desde el navegador (con respaldo del backend), y dos gráficos nuevos: predicciones pasadas vs. real (mañana y final) y evolución del modelo (error °C + tendencia y tasa de acierto).

**Architecture:** El backend (`src/export.py`) agrega dos campos al `data.json` derivados de los CSV existentes. El frontend (`docs/`) se reorganiza en dos zonas; un módulo nuevo `docs/live.js` llama directo a `api.weather.com` cada 30 min para la temperatura actual y la curva de hoy, con respaldo a `data.json` si falla. No se toca el modelo, los workflows ni los CSV.

**Tech Stack:** Python 3.12 + pandas (backend, tests con pytest); HTML/CSS/JS vanilla + Chart.js 4.4.1 (CDN) en `docs/`.

## Global Constraints

- **No tocar** el modelo predictivo, los features, el entrenamiento, el backfill, los workflows de GitHub Actions, ni los CSV de `data/`.
- Python objetivo **3.12**; **sin dependencias nuevas** (solo pandas/stdlib ya presentes).
- Frontend **sin build y sin Node**: HTML/CSS/JS plano + Chart.js **4.4.1** por CDN (ya incluido). Estilo minimalista actual.
- Zona horaria **America/Panama = UTC−5 fijo** (sin horario de verano).
- apiKey de weather.com: **clave pública** `e1f10a1e78da46f5b10a1e78da96f525` (la de los widgets de Wunderground); va embebida como constante en `docs/live.js`.
- Contrato `data.json`: se **conservan** `hoy, generado, temp_actual, pico_hoy, curva_hoy, convergencia_hoy, error_por_hora`; se **elimina** `observados_recientes`; se **agregan** `pasadas_vs_real` y `evolucion_modelo` (formas exactas en las Tasks 1–3).
- **Entorno de ejecución:** el repo no está clonado en la sesión. Ejecutar en un clon/worktree local (o cloud) para correr `pytest`; alternativamente, los commits vía MCP disparan el workflow **Tests** (`tests.yml`) en el PR. Los pasos muestran los comandos `pytest`/`git` locales estándar.
- **Commits frecuentes**, conventional commits, y cada mensaje termina con el trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Spec de referencia: `docs/superpowers/specs/2026-06-25-dashboard-reestructuracion-visualizacion-design.md`.

---

## File Structure

- `src/export.py` (modificar) — dos builders nuevos + integración en `construir_payload`. **Responsabilidad:** construir el payload del dashboard.
- `tests/test_export.py` (modificar) — tests de los builders nuevos y del payload.
- `docs/live.js` (crear) — lectura en vivo de MPMG desde weather.com (fetch + parseo + agenda). **Responsabilidad:** capa "en vivo" del cliente.
- `docs/index.html` (modificar) — estructura de dos zonas y los contenedores/canvas.
- `docs/app.js` (modificar) — render de todo el dashboard desde `data.json` + integración de la capa en vivo.

`src/predict.py` **no cambia**: ya pasa `predicciones`, `observaciones` y `evaluacion` a `construir_payload`, así que los builders nuevos se calculan dentro de `construir_payload` (menos superficie tocada que lo insinuado en la sección 6 del spec).

---

## Task 1: Builder `construir_pasadas_vs_real`

**Files:**
- Modify: `src/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `predicciones` (cols `fecha_objetivo, hora_decision, pico_pred, p10, p90, …`), `observaciones` (cols `fecha, temp_max_c`).
- Produces: `construir_pasadas_vs_real(predicciones: pd.DataFrame, observaciones: pd.DataFrame, n_dias: int = 30) -> list[dict]`, cada dict `{fecha, real, manana_p50, manana_p10, manana_p90, final_p50}`, ascendente por fecha, últimos `n_dias` días con pico real.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_export.py`:

```python
def test_pasadas_vs_real_manana_y_final():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 6,
         "pico_pred": 30.8, "p10": 29.5, "p90": 32.5, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 16,
         "pico_pred": 31.6, "p10": 29.8, "p90": 33.0, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-20", "temp_max_c": 33.0}])
    out = export.construir_pasadas_vs_real(predicciones, observaciones)
    assert out == [{
        "fecha": "2026-06-20", "real": 33.0,
        "manana_p50": 30.8, "manana_p10": 29.5, "manana_p90": 32.5,
        "final_p50": 31.6,
    }]


def test_pasadas_vs_real_excluye_dias_sin_pico_real():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-21", "hora_decision": 6,
         "pico_pred": 30.0, "p10": 29.0, "p90": 31.0, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame(columns=["fecha", "temp_max_c"])
    assert export.construir_pasadas_vs_real(predicciones, observaciones) == []


def test_pasadas_vs_real_un_solo_punto_manana_igual_final():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 9,
         "pico_pred": 31.4, "p10": 30.4, "p90": 32.6, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-22", "temp_max_c": 30.0}])
    out = export.construir_pasadas_vs_real(predicciones, observaciones)
    assert out[0]["manana_p50"] == 31.4 and out[0]["final_p50"] == 31.4
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `python -m pytest tests/test_export.py -k pasadas -v`
Expected: FAIL con `AttributeError: module 'src.export' has no attribute 'construir_pasadas_vs_real'`.

- [ ] **Step 3: Implementar el builder**

Agregar en `src/export.py` (antes de `construir_payload`):

```python
def construir_pasadas_vs_real(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                              n_dias: int = 30) -> list[dict]:
    """Por día con pico real: predicción de la mañana (hora de decisión mínima),
    su banda, y la predicción final (hora máxima), contra el pico real.

    Devuelve los últimos `n_dias` días, ascendente por fecha.
    """
    if len(predicciones) == 0 or len(observaciones) == 0:
        return []
    real = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for fecha, grupo in predicciones.groupby("fecha_objetivo"):
        if fecha not in real:
            continue
        g = grupo.sort_values("hora_decision")
        manana, final = g.iloc[0], g.iloc[-1]
        filas.append({
            "fecha": fecha,
            "real": round(float(real[fecha]), 1),
            "manana_p50": round(float(manana["pico_pred"]), 1),
            "manana_p10": round(float(manana["p10"]), 1),
            "manana_p90": round(float(manana["p90"]), 1),
            "final_p50": round(float(final["pico_pred"]), 1),
        })
    filas.sort(key=lambda r: r["fecha"])
    return filas[-n_dias:]
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `python -m pytest tests/test_export.py -k pasadas -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat(export): builder de predicciones pasadas vs real" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Builder `construir_evolucion`

**Files:**
- Modify: `src/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `evaluacion` (cols `fecha_objetivo, hora_decision, pico_pred, pico_real, error_c`); `config.UMBRAL_ACIERTO_C` (=1.5).
- Produces: `construir_evolucion(evaluacion: pd.DataFrame, ventana: int = 7, umbral: float = config.UMBRAL_ACIERTO_C) -> list[dict]`, cada dict `{fecha, err_manana, err_final, mae7_manana, mae7_final, acierto7_manana, acierto7_final}`, ascendente por fecha. `err_*`/`mae7_*` en °C (2 decimales); `acierto7_*` fracción 0–1 (3 decimales).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_export.py`:

```python
def test_evolucion_error_y_rolling():
    evaluacion = pd.DataFrame([
        {"fecha_objetivo": "2026-06-01", "hora_decision": 6,  "pico_pred": 0, "pico_real": 0, "error_c": 2.0},
        {"fecha_objetivo": "2026-06-01", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": -0.5},
        {"fecha_objetivo": "2026-06-02", "hora_decision": 6,  "pico_pred": 0, "pico_real": 0, "error_c": -1.0},
        {"fecha_objetivo": "2026-06-02", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": 0.2},
    ])
    out = export.construir_evolucion(evaluacion, ventana=7, umbral=1.5)
    assert out[0] == {"fecha": "2026-06-01", "err_manana": 2.0, "err_final": 0.5,
                      "mae7_manana": 2.0, "mae7_final": 0.5,
                      "acierto7_manana": 0.0, "acierto7_final": 1.0}
    assert out[1] == {"fecha": "2026-06-02", "err_manana": 1.0, "err_final": 0.2,
                      "mae7_manana": 1.5, "mae7_final": 0.35,
                      "acierto7_manana": 0.5, "acierto7_final": 1.0}


def test_evolucion_vacia():
    vacio = pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                  "pico_pred", "pico_real", "error_c"])
    assert export.construir_evolucion(vacio) == []
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `python -m pytest tests/test_export.py -k evolucion -v`
Expected: FAIL con `AttributeError: module 'src.export' has no attribute 'construir_evolucion'`.

- [ ] **Step 3: Implementar el builder**

Agregar en `src/export.py` (después de `construir_pasadas_vs_real`):

```python
def construir_evolucion(evaluacion: pd.DataFrame, ventana: int = 7,
                        umbral: float = config.UMBRAL_ACIERTO_C) -> list[dict]:
    """Serie temporal de desempeño: error absoluto diario (mañana=hora mínima,
    final=hora máxima), su media móvil de `ventana` días, y la tasa de acierto
    móvil (fracción de días con |error| <= `umbral`). Ascendente por fecha.
    """
    if len(evaluacion) == 0:
        return []
    ev = evaluacion.copy()
    ev["abs_err"] = ev["error_c"].abs()
    por_dia = []
    for fecha, grupo in ev.groupby("fecha_objetivo"):
        g = grupo.sort_values("hora_decision")
        em, ef = float(g.iloc[0]["abs_err"]), float(g.iloc[-1]["abs_err"])
        por_dia.append({"fecha": fecha,
                        "err_manana": round(em, 2), "err_final": round(ef, 2),
                        "hit_manana": 1.0 if em <= umbral else 0.0,
                        "hit_final": 1.0 if ef <= umbral else 0.0})
    df = pd.DataFrame(por_dia).sort_values("fecha").reset_index(drop=True)

    def rolling(col):
        return df[col].rolling(ventana, min_periods=1).mean()

    df["mae7_manana"] = rolling("err_manana").round(2)
    df["mae7_final"] = rolling("err_final").round(2)
    df["acierto7_manana"] = rolling("hit_manana").round(3)
    df["acierto7_final"] = rolling("hit_final").round(3)
    return [{"fecha": r["fecha"],
             "err_manana": float(r["err_manana"]), "err_final": float(r["err_final"]),
             "mae7_manana": float(r["mae7_manana"]), "mae7_final": float(r["mae7_final"]),
             "acierto7_manana": float(r["acierto7_manana"]),
             "acierto7_final": float(r["acierto7_final"])}
            for _, r in df.iterrows()]
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `python -m pytest tests/test_export.py -k evolucion -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat(export): builder de evolución del modelo (MAE y acierto móviles)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Integrar los campos nuevos en `construir_payload`

**Files:**
- Modify: `src/export.py` (función `construir_payload`)
- Test: `tests/test_export.py` (actualizar `test_construir_payload_estructura`)

**Interfaces:**
- Consumes: `construir_pasadas_vs_real`, `construir_evolucion` (Tasks 1–2).
- Produces: `data.json` con llaves nuevas `pasadas_vs_real`, `evolucion_modelo`; sin `observados_recientes`. Firma de `construir_payload` sin cambios.

- [ ] **Step 1: Actualizar el test de estructura para exigir el contrato nuevo**

En `tests/test_export.py`, dentro de `test_construir_payload_estructura`, reemplazar la línea final `assert "error_por_hora" in payload` por:

```python
    assert "error_por_hora" in payload
    assert "pasadas_vs_real" in payload
    assert "evolucion_modelo" in payload
    assert "observados_recientes" not in payload
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_export.py::test_construir_payload_estructura -v`
Expected: FAIL en `assert "pasadas_vs_real" in payload` (KeyError/AssertionError).

- [ ] **Step 3: Modificar `construir_payload`**

En `src/export.py`, dentro de `construir_payload`, **eliminar** la línea:

```python
    observados = [{"fecha": r["fecha"], "temp_max_c": float(r["temp_max_c"])}
                  for _, r in observaciones.tail(30).iterrows()]
```

y reemplazar el `return { … }` por:

```python
    return {
        "hoy": hoy,
        "generado": generado,
        "temp_actual": temp_actual,
        "pico_hoy": pico_hoy,
        "curva_hoy": curva_hoy or [],
        "convergencia_hoy": convergencia,
        "error_por_hora": error_por_hora,
        "pasadas_vs_real": construir_pasadas_vs_real(predicciones, observaciones),
        "evolucion_modelo": construir_evolucion(evaluacion),
    }
```

(Se quita la llave `observados_recientes`.)

- [ ] **Step 4: Correr toda la suite de export y verificar que pasa**

Run: `python -m pytest tests/test_export.py -v`
Expected: PASS (todos: los previos + Tasks 1–2 + estructura actualizada).

- [ ] **Step 5: Correr la suite completa (no romper nada)**

Run: `python -m pytest -v`
Expected: PASS (toda la suite del repo).

- [ ] **Step 6: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat(export): publicar pasadas_vs_real y evolucion_modelo; retirar observados_recientes" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Capa en vivo `docs/live.js`

**Files:**
- Create: `docs/live.js`

**Interfaces:**
- Produces (global `window.Live`): `fetchEnVivo() -> Promise<{fechaIso, actual, curva}>` donde `actual` es `{temp_c, hora_local, ts}|null` y `curva` es `[{hora, temp_c}]`; `iniciarEnVivo(onUpdate)` que llama `onUpdate({actual, curva, fechaIso})` al cargar, cada 30 min y al reenfocar; helpers puros `parseActual`, `parseCurva`, `fechaHoyPanama`.
- Consumes: API pública `https://api.weather.com/v1/location/MPMG:9:PA/observations/historical.json?apiKey=…&units=m&startDate=YYYYMMDD`.

- [ ] **Step 1: Crear `docs/live.js`**

```js
// docs/live.js
// Lectura en vivo de la estación MPMG desde la API pública de weather.com.
// Misma fuente y lógica que src/sources/wunderground.py (parse_actual /
// parse_curva_intradia), portada a JS para refrescar el navegador cada 30 min
// sin esperar al backend. Si algo falla, la página mantiene el respaldo de data.json.
(function () {
  const API_KEY = "e1f10a1e78da46f5b10a1e78da96f525"; // clave pública de los widgets de Wunderground
  const ESTACION = "MPMG:9:PA";
  const OFFSET_PANAMA_S = 5 * 3600;     // America/Panama = UTC-5 fijo (sin horario de verano)
  const REFRESCO_MS = 30 * 60 * 1000;   // 30 min

  // Date en "hora de pared" de Panamá: se le resta el offset y luego se leen los campos UTC.
  function _local(ts) { return new Date((ts - OFFSET_PANAMA_S) * 1000); }
  function localHour(ts) { return _local(ts).getUTCHours(); }
  function localHHMM(ts) {
    const d = _local(ts);
    return String(d.getUTCHours()).padStart(2, "0") + ":" +
           String(d.getUTCMinutes()).padStart(2, "0");
  }
  function localDateIso(ts) {
    const d = _local(ts);
    return d.getUTCFullYear() + "-" +
           String(d.getUTCMonth() + 1).padStart(2, "0") + "-" +
           String(d.getUTCDate()).padStart(2, "0");
  }

  function fechaHoyPanama(now) {
    const ts = Math.floor((now || new Date()).getTime() / 1000);
    const iso = localDateIso(ts);
    return { iso, compact: iso.replace(/-/g, "") };
  }

  function parseActual(observations, fechaIso) {
    let mejor = null;
    for (const o of observations || []) {
      if (o.temp == null || o.valid_time_gmt == null) continue;
      if (localDateIso(o.valid_time_gmt) !== fechaIso) continue;
      if (mejor === null || o.valid_time_gmt > mejor.valid_time_gmt) mejor = o;
    }
    if (!mejor) return null;
    return {
      temp_c: Math.round(mejor.temp * 10) / 10,
      hora_local: localHHMM(mejor.valid_time_gmt),
      ts: mejor.valid_time_gmt,
    };
  }

  function parseCurva(observations, fechaIso) {
    const porHora = {};
    for (const o of observations || []) {
      if (o.temp == null || o.valid_time_gmt == null) continue;
      if (localDateIso(o.valid_time_gmt) !== fechaIso) continue;
      const h = localHour(o.valid_time_gmt);
      if (!(h in porHora) || o.temp > porHora[h]) porHora[h] = o.temp;
    }
    return Object.keys(porHora).map(Number).sort((a, b) => a - b)
      .map((h) => ({ hora: h, temp_c: Math.round(porHora[h] * 10) / 10 }));
  }

  async function fetchEnVivo() {
    const { iso, compact } = fechaHoyPanama();
    const url = `https://api.weather.com/v1/location/${ESTACION}/observations/historical.json`
      + `?apiKey=${API_KEY}&units=m&startDate=${compact}`;
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) throw new Error(`weather.com HTTP ${resp.status}`);
    const data = await resp.json();
    const obs = data.observations || [];
    return { fechaIso: iso, actual: parseActual(obs, iso), curva: parseCurva(obs, iso) };
  }

  function iniciarEnVivo(onUpdate) {
    const correr = async () => {
      try {
        const datos = await fetchEnVivo();
        if (datos.actual || datos.curva.length) onUpdate(datos);
      } catch (e) {
        console.warn("Live fetch falló, se mantiene el respaldo de data.json:", e.message);
      }
    };
    correr();
    setInterval(correr, REFRESCO_MS);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") correr();
    });
  }

  window.Live = { fetchEnVivo, iniciarEnVivo, parseActual, parseCurva, fechaHoyPanama };
})();
```

- [ ] **Step 2: Verificar el parseo contra una muestra (sin Node, en la consola del navegador)**

Abrir cualquier página (o `about:blank`), pegar el cuerpo de las funciones `_local/localHour/localHHMM/localDateIso/parseActual/parseCurva` en la consola y correr:

```js
const obs = [
  { temp: 26, valid_time_gmt: 1750770000 }, // 2026-06-24 11:00 UTC ≈ 06:00 Panamá
  { temp: 32, valid_time_gmt: 1750795200 }, // 2026-06-24 18:00 UTC ≈ 13:00 Panamá
];
console.log(parseActual(obs, "2026-06-24")); // => { temp_c: 32, hora_local: "13:00", ts: 1750795200 }
console.log(parseCurva(obs, "2026-06-24"));  // => [{hora:6,temp_c:26},{hora:13,temp_c:32}]
```
Expected: la última observación manda en `parseActual`; `parseCurva` agrupa por hora local. Si no coincide, revisar el offset.

- [ ] **Step 3: Verificar el fetch real en el navegador**

Servir `docs/` localmente (sin Node): `python -m http.server -d docs 8000`, abrir `http://localhost:8000`, y en la consola correr `await Live.fetchEnVivo()`. Confirmar que devuelve `{actual:{temp_c,hora_local,ts}, curva:[…]}` y que `temp_c` coincide con lo que muestra https://www.wunderground.com/weather/pa/panama-city/MPMG.

- [ ] **Step 4: Commit**

```bash
git add docs/live.js
git commit -m "feat(dashboard): capa en vivo de MPMG desde weather.com (refresco 30 min)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Reestructurar `docs/index.html` en dos zonas

**Files:**
- Modify: `docs/index.html` (reemplazo completo)

**Interfaces:**
- Produces (IDs/canvas que consume `app.js`): `#ahora-num, #ahora-meta, #ahora-sello, #pico-num, #pico-banda, #pico-meta, #curva, #pasadas, #pasadas-nota, #evo-error, #evo-acierto, #evo-nota, #error, #hoy, #generado`. Carga `./live.js` antes de `./app.js`.

- [ ] **Step 1: Reemplazar `docs/index.html` por completo**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Temperatura de hoy — Ciudad de Panamá (MPMG)</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.4rem; }
    .zona-tit { font-size: .8rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
                color: #57606a; border-bottom: 2px solid #eaeef2; padding-bottom: .3rem; margin: 2.2rem 0 .8rem; }
    .zona-tit.envivo { color: #1a7f37; border-color: #d2f0d9; }
    .zona-tit.desempeno { color: #0969da; border-color: #d7e8fb; }
    h2 { font-size: 1.05rem; margin-top: 1.6rem; }
    p.sub { font-size: .85rem; color: #666; margin-top: .2rem; }
    .hero { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1rem 0; }
    .card { border: 1px solid #e1e4e8; border-radius: 14px; padding: 1.2rem; text-align: center; }
    .card.ahora { background: #f0fbf3; border-color: #cfead7; }
    .card.pico  { background: #fff5f5; border-color: #ffd7d5; }
    .rotulo { font-size: .75rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
    .card.ahora .rotulo { color: #1a7f37; }
    .card.pico  .rotulo { color: #cf222e; }
    .num { font-size: 2.8rem; font-weight: 800; line-height: 1; margin-top: .25rem; }
    .card.ahora .num { color: #1a7f37; }
    .card.pico  .num { color: #cf222e; }
    .meta { font-size: .82rem; color: #888; margin-top: .35rem; }
    .sello { font-size: .72rem; color: #9aa0a6; margin-top: .3rem; }
    .sello.retraso { color: #bf8700; }
    @media (max-width: 520px) { .hero { grid-template-columns: 1fr; } }
    canvas { margin-top: .5rem; }
    .nota-vacia { font-size: .85rem; color: #999; font-style: italic; }
    footer { margin-top: 2.5rem; font-size: .8rem; color: #888; }
  </style>
</head>
<body>
  <h1>🌡️ Temperatura de hoy — Ciudad de Panamá (MPMG · Marcos A. Gelabert)</h1>

  <div class="zona-tit envivo">En vivo</div>
  <div class="hero">
    <div class="card ahora">
      <div class="rotulo">Ahora en la estación</div>
      <div class="num" id="ahora-num">—</div>
      <div class="meta" id="ahora-meta"></div>
      <div class="sello" id="ahora-sello"></div>
    </div>
    <div class="card pico">
      <div class="rotulo">Pico máximo previsto hoy</div>
      <div class="num" id="pico-num">—</div>
      <div class="meta" id="pico-banda"></div>
      <div class="sello" id="pico-meta"></div>
    </div>
  </div>

  <h2>La temperatura de hoy y el pico previsto</h2>
  <p class="sub">La línea es la temperatura observada hoy hora a hora en MPMG; la banda punteada es el pico máximo previsto, que suele alcanzarse entre 12 y 2 pm.</p>
  <canvas id="curva" height="130"></canvas>

  <div class="zona-tit desempeno">Desempeño del modelo</div>

  <h2>Predicciones pasadas vs. real</h2>
  <p class="sub">Para cada día: el pico real, la predicción de la mañana (~6am, con su banda) y la predicción final (~4pm). Cuanto más cerca del real, mejor.</p>
  <canvas id="pasadas" height="120"></canvas>
  <p class="nota-vacia" id="pasadas-nota" hidden>Se llenará conforme se acumulen días con pico real.</p>

  <h2>Evolución del modelo</h2>
  <p class="sub">Error absoluto por día con su media móvil de 7 días (¿el error baja?).</p>
  <canvas id="evo-error" height="110"></canvas>
  <p class="sub">Tasa de acierto: % de días dentro de ±1.5 °C, media móvil de 7 días (¿sube?).</p>
  <canvas id="evo-acierto" height="110"></canvas>
  <p class="nota-vacia" id="evo-nota" hidden>Se llenará conforme se acumulen días evaluados.</p>

  <h2>Precisión según la hora de decisión</h2>
  <p class="sub">Error absoluto medio del pico previsto según a qué hora se predijo (más tarde en el día → más certero).</p>
  <canvas id="error" height="100"></canvas>

  <footer>Día: <span id="hoy"></span> · Última actualización del modelo: <span id="generado">—</span> · Modelo: LightGBM cuantiles · Datos: Open-Meteo + Wunderground (MPMG)</footer>

  <script src="./live.js"></script>
  <script src="./app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verificación visual de la estructura**

Con `python -m http.server -d docs 8000` abrir `http://localhost:8000`: deben verse los encabezados **En vivo** y **Desempeño**, las dos tarjetas (Ahora / Pico) lado a lado, y al estrechar la ventana (<520px) deben apilarse. Los canvas aún pueden estar vacíos (los pinta `app.js` en la Task 6).

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat(dashboard): reestructura en zonas En vivo / Desempeño" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Reescribir `docs/app.js` (render de zonas + integración en vivo)

**Files:**
- Modify: `docs/app.js` (reemplazo completo)

**Interfaces:**
- Consumes: `data.json` (con `pasadas_vs_real`, `evolucion_modelo` de Task 3), `window.Live` (Task 4), IDs/canvas de `index.html` (Task 5).
- Produces: dashboard renderizado; AHORA y curva refrescados en vivo con respaldo de `data.json`.

- [ ] **Step 1: Reemplazar `docs/app.js` por completo**

```js
const HMIN = 6, HMAX = 18;
let curvaChart = null;

async function cargar() {
  const datos = await fetch('./data.json?v=' + Date.now()).then(r => r.json());
  document.getElementById('hoy').textContent = datos.hoy || '';
  pintarGenerado(datos.generado);

  pintarPico(datos.pico_hoy);
  pintarAhora(datos.temp_actual, false);           // respaldo inicial; el fetch en vivo lo pisa

  curvaChart = crearCurva(datos.curva_hoy || [], datos.pico_hoy);
  renderPasadas(datos.pasadas_vs_real || []);
  renderEvolucion(datos.evolucion_modelo || []);
  renderErrorPorHora(datos.error_por_hora || []);

  if (window.Live) {
    window.Live.iniciarEnVivo((d) => {
      if (d.actual) pintarAhora(d.actual, true);
      if (d.curva && d.curva.length) actualizarCurva(d.curva);
    });
  }
}

function pintarGenerado(generado) {
  if (!generado) return;
  const fmt = new Date(generado).toLocaleString('es-PA', {
    timeZone: 'America/Panama', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit', hour12: false,
  });
  document.getElementById('generado').textContent = fmt + ' (Panamá)';
}

function pintarPico(p) {
  const num = document.getElementById('pico-num');
  const banda = document.getElementById('pico-banda');
  const meta = document.getElementById('pico-meta');
  if (!p) {
    num.textContent = '—';
    banda.textContent = '';
    meta.textContent = 'aún sin predicción para hoy';
    return;
  }
  num.textContent = p.pico_pred.toFixed(1) + '°C';
  banda.textContent = `banda ${p.p10.toFixed(1)}° – ${p.p90.toFixed(1)}°`;
  meta.textContent = `estimado a las ${p.hora_decision}:00 · se afina cada hora`;
}

function pintarAhora(actual, enVivo) {
  const num = document.getElementById('ahora-num');
  const meta = document.getElementById('ahora-meta');
  const sello = document.getElementById('ahora-sello');
  if (!actual) {
    num.textContent = '—';
    meta.textContent = '';
    sello.textContent = 'sin dato de la estación ahora mismo';
    sello.classList.remove('retraso');
    return;
  }
  num.textContent = actual.temp_c.toFixed(1) + '°C';
  meta.textContent = 'MPMG · ' + actual.hora_local;
  if (enVivo && actual.ts) {
    const min = Math.max(0, Math.round(Date.now() / 1000 / 60 - actual.ts / 60));
    if (min > 90) {
      sello.textContent = `dato con retraso (hace ${min} min)`;
      sello.classList.add('retraso');
    } else {
      sello.textContent = `actualizado hace ${min} min · ↻ cada 30 min`;
      sello.classList.remove('retraso');
    }
  } else {
    sello.textContent = '↻ cada 30 min';
    sello.classList.remove('retraso');
  }
}

function datasetObs(curva) {
  const porHora = {};
  (curva || []).forEach(r => { porHora[r.hora] = r.temp_c; });
  const data = [];
  for (let h = HMIN; h <= HMAX; h++) data.push(h in porHora ? porHora[h] : null);
  return { label: 'Temperatura observada hoy', data, borderColor: '#1a7f37',
           backgroundColor: '#1a7f37', borderWidth: 2, tension: .3, spanGaps: false, pointRadius: 2 };
}

function crearCurva(curva, p) {
  const labels = [];
  for (let h = HMIN; h <= HMAX; h++) labels.push(h + ':00');
  const datasets = [datasetObs(curva)];
  if (p) {
    const n = labels.length;
    datasets.push(
      { label: 'Pico previsto (p90)', data: Array(n).fill(p.p90),
        borderColor: 'rgba(207,34,46,.25)', borderDash: [4, 4], pointRadius: 0,
        fill: '+1', backgroundColor: 'rgba(207,34,46,.08)' },
      { label: 'Pico previsto (p10)', data: Array(n).fill(p.p10),
        borderColor: 'rgba(207,34,46,.25)', borderDash: [4, 4], pointRadius: 0 },
      { label: 'Pico previsto (p50)', data: Array(n).fill(p.pico_pred),
        borderColor: '#cf222e', borderDash: [6, 3], borderWidth: 1.5, pointRadius: 0 },
    );
  }
  return new Chart(document.getElementById('curva'), {
    type: 'line',
    data: { labels, datasets },
    options: { scales: { y: { title: { display: true, text: '°C' } },
                         x: { title: { display: true, text: 'hora del día (Panamá)' } } } },
  });
}

function actualizarCurva(curva) {
  if (!curvaChart) return;
  curvaChart.data.datasets[0] = datasetObs(curva);
  curvaChart.update();
}

function renderPasadas(arr) {
  const nota = document.getElementById('pasadas-nota');
  if (!arr.length) { nota.hidden = false; return; }
  nota.hidden = true;
  const labels = arr.map(r => r.fecha.slice(5));
  new Chart(document.getElementById('pasadas'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Mañana p90', data: arr.map(r => r.manana_p90),
          borderColor: 'rgba(9,105,218,.18)', pointRadius: 0, fill: '+1',
          backgroundColor: 'rgba(9,105,218,.08)' },
        { label: 'Mañana p10', data: arr.map(r => r.manana_p10),
          borderColor: 'rgba(9,105,218,.18)', pointRadius: 0 },
        { label: 'Predicción mañana', data: arr.map(r => r.manana_p50),
          borderColor: '#0969da', borderDash: [5, 3], tension: .2, pointRadius: 2 },
        { label: 'Predicción final', data: arr.map(r => r.final_p50),
          borderColor: '#8250df', tension: .2, pointRadius: 2 },
        { label: 'Pico real', data: arr.map(r => r.real),
          borderColor: '#1a7f37', borderWidth: 2.5, tension: .2, pointRadius: 3 },
      ],
    },
    options: { scales: { y: { title: { display: true, text: '°C' } } } },
  });
}

function renderEvolucion(arr) {
  const nota = document.getElementById('evo-nota');
  if (!arr.length) { nota.hidden = false; return; }
  nota.hidden = true;
  const labels = arr.map(r => r.fecha.slice(5));

  new Chart(document.getElementById('evo-error'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Error mañana (día)', data: arr.map(r => r.err_manana),
          borderColor: 'rgba(9,105,218,.25)', pointRadius: 0, tension: .2 },
        { label: 'Tendencia mañana (7d)', data: arr.map(r => r.mae7_manana),
          borderColor: '#0969da', borderWidth: 2, pointRadius: 0, tension: .3 },
        { label: 'Error final (día)', data: arr.map(r => r.err_final),
          borderColor: 'rgba(130,80,223,.25)', pointRadius: 0, tension: .2 },
        { label: 'Tendencia final (7d)', data: arr.map(r => r.mae7_final),
          borderColor: '#8250df', borderWidth: 2, pointRadius: 0, tension: .3 },
      ],
    },
    options: { scales: { y: { beginAtZero: true, title: { display: true, text: '°C de error' } } } },
  });

  new Chart(document.getElementById('evo-acierto'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Acierto mañana (7d)', data: arr.map(r => Math.round(r.acierto7_manana * 100)),
          borderColor: '#0969da', borderWidth: 2, pointRadius: 0, tension: .3 },
        { label: 'Acierto final (7d)', data: arr.map(r => Math.round(r.acierto7_final * 100)),
          borderColor: '#8250df', borderWidth: 2, pointRadius: 0, tension: .3 },
      ],
    },
    options: { scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: '% dentro de ±1.5°C' } } } },
  });
}

function renderErrorPorHora(arr) {
  new Chart(document.getElementById('error'), {
    type: 'bar',
    data: {
      labels: arr.map(r => r.hora_decision + ':00'),
      datasets: [{ label: 'Error medio abs (°C)', data: arr.map(r => r.error_medio_abs),
                   backgroundColor: '#57606a' }],
    },
    options: { scales: { y: { beginAtZero: true, title: { display: true, text: '°C' } } } },
  });
}

cargar();
```

- [ ] **Step 2: Verificación visual completa (local, sin Node)**

Con `python -m http.server -d docs 8000` abrir `http://localhost:8000` y confirmar:
- Zona **En vivo**: AHORA muestra un número (de `data.json` y luego refrescado en vivo — ver la pestaña Network: una llamada a `api.weather.com`), con el sello "actualizado hace X min". El PICO muestra `pico_hoy`. La curva de hoy se dibuja en verde con la banda roja del pico.
- Zona **Desempeño**: el gráfico "pasadas vs real" muestra 3 series + banda tenue de la mañana; los dos mini-gráficos de evolución (error y acierto) y el secundario de precisión por hora aparecen.
- Forzar respaldo: en la consola, `window.Live = undefined` antes de recargar (o bloquear `api.weather.com` en Network) → la página sigue mostrando AHORA desde `data.json` sin romperse.

- [ ] **Step 3: Verificar que `data.json` actual aún renderiza (compatibilidad)**

El `docs/data.json` versionado todavía no trae `pasadas_vs_real`/`evolucion_modelo` (se generan en la próxima corrida del backend). Confirmar que, sin esos campos, "pasadas" y "evolución" muestran su nota *"se llenará…"* en vez de error. (El backend los poblará en su próximo run; opcionalmente, regenerar `data.json` local con `python -m src.predict` si se tiene el entorno.)

- [ ] **Step 4: Commit**

```bash
git add docs/app.js
git commit -m "feat(dashboard): render de las dos zonas y gráficos de desempeño con capa en vivo" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificación final (tras integrar las 6 tasks)

- [ ] `python -m pytest -v` en verde (o el workflow **Tests** del PR).
- [ ] Servir `docs/` y revisar las dos zonas, el refresco en vivo (Network → `api.weather.com` cada 30 min / al reenfocar) y los respaldos.
- [ ] Abrir PR de `feat/dashboard-reestructuracion` → `main` (vía MCP de GitHub). Al hacer merge, el workflow **Pages** publica; la próxima corrida de `hourly.yml` regenera `data.json` con los campos nuevos.

## Notas de implementación

- **Orden:** Tasks 1→2→3 (backend, independientes del frontend) y 4→5→6 (frontend; 6 depende de 4 y 5). 4 y 5 pueden ir en paralelo a 1–3.
- **Sin tocar** `src/predict.py`, workflows, modelo ni CSV.
- Si el fetch en vivo fallara de forma persistente en producción, el respaldo (`data.json.temp_actual`/`curva_hoy`, horario) mantiene la página; reconsiderar entonces un job de backend de 30 min (fuera de alcance ahora).
