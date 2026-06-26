# % de acierto + tabla histórica — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al dashboard un % de acierto histórico junto al pico previsto y una tabla de las últimas 20 predicciones (1 por día), ambos derivados de `evaluation.csv`/`predictions.csv`/`observations.csv`.

**Architecture:** El backend (`src/export.py`) calcula el acierto por hora de decisión y lo adjunta a `pico_hoy`, y agrega `tabla_historica` al `data.json`. El frontend (`docs/`) muestra una línea de probabilidad en la tarjeta del pico y una tabla HTML en la zona Desempeño. Construye sobre el dashboard ya en `main`. No se toca el modelo, los workflows ni los CSV.

**Tech Stack:** Python 3.12 + pandas (backend, pytest); HTML/CSS/JS vanilla en `docs/` (la tabla es HTML, no Chart.js).

## Global Constraints

- **No tocar** el modelo, features, entrenamiento, backfill, workflows ni los CSV de `data/`.
- Python **3.12**; **sin dependencias nuevas**.
- Umbral de acierto: **±1.5°C** = `config.UMBRAL_ACIERTO_C`.
- `data.json` gana: `pico_hoy.prob_acierto` (entero 0–100 o `null`), `pico_hoy.prob_n` (entero o `null`), y `tabla_historica` (lista; ver Task 2). Nada existente se elimina.
- `tabla_historica` ordenada **descendente por fecha** (más reciente primero), tope **20**.
- Frontend **sin build/sin Node**: HTML/CSS/JS plano. Estilo minimalista actual.
- **Entorno de ejecución:** repo no clonado en la sesión; ejecutar en clon/worktree local para `pytest`, o confiar en el workflow **Tests** del PR. Frontend se sirve con `python -m http.server -d docs 8000`.
- Commits conventional + trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Spec: `docs/superpowers/specs/2026-06-26-dashboard-acierto-y-tabla-historica-design.md`.

---

## File Structure

- `src/export.py` (modificar) — helper de acierto por hora + adjuntar a `pico_hoy`; builder `construir_tabla_historica`; integrar en `construir_payload`.
- `tests/test_export.py` (modificar) — tests de ambos.
- `docs/index.html` (modificar) — `#pico-prob` en la tarjeta del pico; tabla en Desempeño; estilos.
- `docs/app.js` (modificar) — línea de probabilidad en `pintarPico`; `renderTablaHistorica` llamada desde `refrescarDatos`.

---

## Task 1: Acierto por hora adjunto a `pico_hoy`

**Files:**
- Modify: `src/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Produces: helper `_acierto_hora(evaluacion, hora, umbral=config.UMBRAL_ACIERTO_C) -> tuple` que devuelve `(pct_entero, n)` o `(None, None)`; `construir_payload` adjunta `pico_hoy["prob_acierto"]` y `pico_hoy["prob_n"]`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_export.py`:

```python
def test_pico_hoy_incluye_prob_acierto():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-16", "hora_decision": 16,
         "pico_pred": 33.0, "p10": 32.0, "p90": 34.0, "modelo_version": "v"},
    ])
    # A la hora 16: 3 días, 2 dentro de ±1.5 -> 67%
    evaluacion = pd.DataFrame([
        {"fecha_objetivo": "2026-06-13", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": 0.5},
        {"fecha_objetivo": "2026-06-14", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": -1.0},
        {"fecha_objetivo": "2026-06-15", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": 2.0},
    ])
    obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    payload = export.construir_payload(predicciones, obs, evaluacion, hoy="2026-06-16")
    assert payload["pico_hoy"]["prob_acierto"] == 67
    assert payload["pico_hoy"]["prob_n"] == 3


def test_pico_hoy_prob_acierto_null_sin_historial():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-16", "hora_decision": 7,
         "pico_pred": 33.0, "p10": 32.0, "p90": 34.0, "modelo_version": "v"},
    ])
    evaluacion = pd.DataFrame([
        {"fecha_objetivo": "2026-06-13", "hora_decision": 16, "pico_pred": 0, "pico_real": 0, "error_c": 0.5},
    ])
    obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    payload = export.construir_payload(predicciones, obs, evaluacion, hoy="2026-06-16")
    assert payload["pico_hoy"]["prob_acierto"] is None
    assert payload["pico_hoy"]["prob_n"] is None
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `python -m pytest tests/test_export.py -k prob_acierto -v`
Expected: FAIL (`KeyError: 'prob_acierto'`).

- [ ] **Step 3: Implementar**

En `src/export.py`, agregar el helper antes de `construir_payload`:

```python
def _acierto_hora(evaluacion: pd.DataFrame, hora: int,
                  umbral: float = config.UMBRAL_ACIERTO_C) -> tuple:
    """(% de acierto entero, n) de las predicciones hechas a `hora`.

    Acierto = |error_c| <= umbral. Devuelve (None, None) si esa hora no tiene
    historial evaluado.
    """
    if len(evaluacion) == 0:
        return (None, None)
    sub = evaluacion[evaluacion["hora_decision"] == hora]
    if len(sub) == 0:
        return (None, None)
    pct = (sub["error_c"].abs() <= umbral).mean()
    return (round(float(pct) * 100), int(len(sub)))
```

En `construir_payload`, dentro del bloque `if len(hoy_preds):`, justo después de crear `pico_hoy = {...}`, agregar:

```python
        prob_acierto, prob_n = _acierto_hora(evaluacion, int(ult["hora_decision"]))
        pico_hoy["prob_acierto"] = prob_acierto
        pico_hoy["prob_n"] = prob_n
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `python -m pytest tests/test_export.py -k prob_acierto -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat(export): adjunta % de acierto histórico por hora a pico_hoy" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Builder `construir_tabla_historica` + integración

**Files:**
- Modify: `src/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Produces: `construir_tabla_historica(predicciones, observaciones, n_dias=20) -> list[dict]`, items `{fecha, prediccion, real, se_cumplio, tasa_error_pct, diferencia}`, descendente por fecha, tope `n_dias`. `construir_payload` agrega la llave `tabla_historica`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_export.py`:

```python
def test_tabla_historica_columnas_y_orden():
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 6,  "pico_pred": 30.0, "p10": 29, "p90": 31, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 16, "pico_pred": 31.0, "p10": 30, "p90": 33, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-21", "hora_decision": 16, "pico_pred": 33.0, "p10": 32, "p90": 34, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([
        {"fecha": "2026-06-20", "temp_max_c": 33.0},
        {"fecha": "2026-06-21", "temp_max_c": 33.0},
    ])
    out = export.construir_tabla_historica(predicciones, observaciones)
    assert [r["fecha"] for r in out] == ["2026-06-21", "2026-06-20"]   # más reciente primero
    assert out[1] == {"fecha": "2026-06-20", "prediccion": 31.0, "real": 33.0,
                      "se_cumplio": False, "tasa_error_pct": 6.1, "diferencia": -2.0}
    assert out[0]["se_cumplio"] is True
    assert out[0]["diferencia"] == 0.0
    assert out[0]["tasa_error_pct"] == 0.0


def test_tabla_historica_tope_20():
    preds, obs = [], []
    for i in range(1, 26):
        f = f"2026-05-{i:02d}"
        preds.append({"run_timestamp": "x", "fecha_objetivo": f, "hora_decision": 16,
                      "pico_pred": 30.0, "p10": 29, "p90": 31, "modelo_version": "v"})
        obs.append({"fecha": f, "temp_max_c": 30.0})
    out = export.construir_tabla_historica(pd.DataFrame(preds), pd.DataFrame(obs))
    assert len(out) == 20
    assert out[0]["fecha"] == "2026-05-25"


def test_tabla_historica_vacia():
    vacio_pred = pd.DataFrame(columns=["fecha_objetivo", "hora_decision", "pico_pred", "p10", "p90"])
    vacio_obs = pd.DataFrame(columns=["fecha", "temp_max_c"])
    assert export.construir_tabla_historica(vacio_pred, vacio_obs) == []
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `python -m pytest tests/test_export.py -k tabla_historica -v`
Expected: FAIL (`AttributeError: ... has no attribute 'construir_tabla_historica'`).

- [ ] **Step 3: Implementar**

En `src/export.py`, agregar (después de `construir_evolucion`):

```python
def construir_tabla_historica(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                              n_dias: int = 20) -> list[dict]:
    """Registro por día (predicción final vs pico real) de los últimos `n_dias`
    días con pico real, más reciente primero.
    """
    if len(predicciones) == 0 or len(observaciones) == 0:
        return []
    real = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for fecha, grupo in predicciones.groupby("fecha_objetivo"):
        if fecha not in real:
            continue
        final = grupo.sort_values("hora_decision").iloc[-1]
        pred = round(float(final["pico_pred"]), 1)
        r = round(float(real[fecha]), 1)
        filas.append({
            "fecha": fecha,
            "prediccion": pred,
            "real": r,
            "se_cumplio": abs(pred - r) <= config.UMBRAL_ACIERTO_C,
            "tasa_error_pct": round(abs(pred - r) / r * 100, 1),
            "diferencia": round(pred - r, 1),
        })
    filas.sort(key=lambda x: x["fecha"], reverse=True)
    return filas[:n_dias]
```

En `construir_payload`, en el `return {...}`, agregar la llave (después de `"evolucion_modelo": ...`):

```python
        "tabla_historica": construir_tabla_historica(predicciones, observaciones),
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `python -m pytest tests/test_export.py -v`
Expected: PASS (toda la suite de export, incluidos los nuevos).

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat(export): tabla histórica de las últimas 20 predicciones en data.json" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Frontend — línea de % de acierto en la tarjeta del pico

**Files:**
- Modify: `docs/index.html`, `docs/app.js`

**Interfaces:**
- Consumes: `pico_hoy.prob_acierto` (int|null), `pico_hoy.prob_n` (int|null) (Task 1).
- Produces: elemento `#pico-prob`; `pintarPico` lo rellena.

- [ ] **Step 1: Añadir el contenedor y su estilo en `index.html`**

En `docs/index.html`, dentro de `<div class="card pico">`, insertar `#pico-prob` entre `#pico-banda` y `#pico-meta`:

```html
      <div class="meta" id="pico-banda"></div>
      <div class="prob" id="pico-prob"></div>
      <div class="sello" id="pico-meta"></div>
```

En el `<style>`, agregar (junto a las reglas de `.card.pico`):

```css
    .card.pico .prob { font-size: .85rem; font-weight: 700; color: #cf222e; margin-top: .45rem; }
```

- [ ] **Step 2: Rellenar `#pico-prob` en `app.js`**

En `docs/app.js`, reemplazar la función `pintarPico` completa por:

```js
function pintarPico(p) {
  const num = document.getElementById('pico-num');
  const banda = document.getElementById('pico-banda');
  const prob = document.getElementById('pico-prob');
  const meta = document.getElementById('pico-meta');
  if (!p) {
    num.textContent = '—';
    banda.textContent = '';
    prob.textContent = '';
    meta.textContent = 'aún sin predicción para hoy';
    return;
  }
  num.textContent = p.pico_pred.toFixed(1) + '°C';
  banda.textContent = `banda ${p.p10.toFixed(1)}° – ${p.p90.toFixed(1)}°`;
  if (p.prob_acierto != null) {
    let t = `≈${p.prob_acierto}% probable que este sea el pico · histórico de ${p.prob_n} día${p.prob_n === 1 ? '' : 's'}`;
    if (p.prob_n < 5) t += ' (pocos datos aún)';
    prob.textContent = t;
  } else {
    prob.textContent = '';
  }
  meta.textContent = `estimado a las ${p.hora_decision}:00 · se afina cada hora`;
}
```

- [ ] **Step 3: Verificar visualmente**

`python -m http.server -d docs 8000` → abrir `http://localhost:8000`. Con el `data.json` actual (sin `prob_acierto`) la línea no debe aparecer (sin error). Para probarla, en la consola: `pintarPico({pico_pred:33,p10:32.2,p90:33,hora_decision:14,prob_acierto:80,prob_n:9})` debe mostrar la frase; con `prob_n:3` debe añadir "(pocos datos aún)"; con `prob_acierto:null` no debe mostrar nada.

- [ ] **Step 4: Commit**

```bash
git add docs/index.html docs/app.js
git commit -m "feat(dashboard): muestra el % de acierto histórico junto al pico" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Frontend — tabla de las últimas 20 predicciones

**Files:**
- Modify: `docs/index.html`, `docs/app.js`

**Interfaces:**
- Consumes: `tabla_historica` (Task 2): items `{fecha, prediccion, real, se_cumplio, tasa_error_pct, diferencia}`.
- Produces: tabla `#tabla-historica` + `#tabla-historica-body` + nota `#tabla-nota`; `renderTablaHistorica(arr)` llamada desde `refrescarDatos`.

- [ ] **Step 1: Añadir la tabla y sus estilos en `index.html`**

En `docs/index.html`, justo después del bloque de "Predicciones pasadas vs. real" (tras `<p class="nota-vacia" id="pasadas-nota" ...>`), insertar:

```html
  <h2>Registro de las últimas 20 predicciones</h2>
  <p class="sub">La predicción final de cada día (~4pm) contra el pico real observado.</p>
  <table id="tabla-historica">
    <thead>
      <tr><th>Día</th><th>Predicción</th><th>Pico Real</th><th>Se cumplió</th><th>Tasa de error</th><th>Diferencia</th></tr>
    </thead>
    <tbody id="tabla-historica-body"></tbody>
  </table>
  <p class="nota-vacia" id="tabla-nota" hidden>Se llenará conforme se acumulen días.</p>
```

En el `<style>`, agregar:

```css
    table#tabla-historica { width: 100%; border-collapse: collapse; font-size: .85rem; margin-top: .5rem; }
    #tabla-historica th, #tabla-historica td { padding: .4rem .5rem; text-align: center; border-bottom: 1px solid #eaeef2; }
    #tabla-historica th { color: #57606a; font-weight: 700; text-transform: uppercase; font-size: .7rem; letter-spacing: .03em; }
    #tabla-historica th:first-child, #tabla-historica td:first-child { text-align: left; }
    #tabla-historica .si { color: #1a7f37; font-weight: 600; }
    #tabla-historica .no { color: #cf222e; font-weight: 600; }
```

- [ ] **Step 2: Renderizar la tabla en `app.js`**

En `docs/app.js`, dentro de `refrescarDatos`, después de `renderEvolucion(datos.evolucion_modelo || []);`, agregar:

```js
  renderTablaHistorica(datos.tabla_historica || []);
```

Y agregar la función (junto a las otras `render*`):

```js
function renderTablaHistorica(arr) {
  const body = document.getElementById('tabla-historica-body');
  const nota = document.getElementById('tabla-nota');
  const tabla = document.getElementById('tabla-historica');
  if (!arr.length) { body.innerHTML = ''; tabla.hidden = true; nota.hidden = false; return; }
  tabla.hidden = false; nota.hidden = true;
  body.innerHTML = arr.map(r => {
    const dif = (r.diferencia >= 0 ? '+' : '') + r.diferencia.toFixed(1);
    const cumplio = r.se_cumplio
      ? '<span class="si">✓ Sí</span>'
      : '<span class="no">✗ No</span>';
    return `<tr>
      <td>${r.fecha.slice(5)}</td>
      <td>${r.prediccion.toFixed(1)}°C</td>
      <td>${r.real.toFixed(1)}°C</td>
      <td>${cumplio}</td>
      <td>${r.tasa_error_pct.toFixed(1)}%</td>
      <td>${dif}°C</td>
    </tr>`;
  }).join('');
}
```

- [ ] **Step 3: Verificar visualmente**

`python -m http.server -d docs 8000` → abrir `http://localhost:8000`. Con el `data.json` actual (sin `tabla_historica`) debe verse la nota "se llenará…" y la tabla oculta (sin error). En la consola, probar:
`renderTablaHistorica([{fecha:'2026-06-24',prediccion:33.1,real:33.0,se_cumplio:true,tasa_error_pct:0.3,diferencia:0.1},{fecha:'2026-06-23',prediccion:30.6,real:33.0,se_cumplio:false,tasa_error_pct:7.3,diferencia:-2.4}])` → dos filas, "✓ Sí" verde / "✗ No" rojo, diferencias con signo (`+0.1°C`, `-2.4°C`).

- [ ] **Step 4: Commit**

```bash
git add docs/index.html docs/app.js
git commit -m "feat(dashboard): tabla de las últimas 20 predicciones (predicción vs real)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificación final

- [ ] `python -m pytest -v` en verde (o el workflow **Tests** del PR).
- [ ] Servir `docs/` y revisar la línea de probabilidad en la tarjeta del pico y la tabla en Desempeño; confirmar que con el `data.json` viejo (sin los campos nuevos) nada se rompe.
- [ ] Abrir PR a `main`; al hacer merge, la próxima corrida de `hourly.yml` regenera `data.json` con los campos nuevos.

## Notas

- Orden sugerido: Task 1 → 2 (backend) → 3 → 4 (frontend). 3 y 4 son independientes entre sí.
- `_acierto_hora` usa `error_c` de `evaluation.csv`; `construir_tabla_historica` usa la predicción final por día. Ambos con umbral ±1.5°C. Sin cambios en `predict.py` (los builders corren dentro de `construir_payload`).
