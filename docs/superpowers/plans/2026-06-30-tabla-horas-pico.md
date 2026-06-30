# Tabla histórica: hora de predicción y hora del pico — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir a la tabla histórica del dashboard las columnas Hora pred., Hora pico y ¿Antes?, para ver si la predicción se fijó antes de que ocurriera el pico.

**Architecture:** La hora de predicción y "¿antes?" se derivan en `export.py` (puro). La hora del pico real sale de la estación (weather.com) cacheada en `data/peak_hours.csv`, que `predict.py` rellena con una sola llamada por rango. El frontend pinta 3 columnas nuevas. No se toca el modelo ni los workflows.

**Tech Stack:** Python 3.12 + pandas + requests (backend, pytest); HTML/CSS/JS vanilla en `docs/`.

## Global Constraints

- **No tocar** el modelo, features, entrenamiento ni los workflows. (`hourly.yml` ya hace `git add data/`, así que `data/peak_hours.csv` se commitea solo.)
- Python **3.12**, **sin dependencias nuevas**.
- `data.json` → cada item de `tabla_historica` gana: `hora_prediccion` (int 0–23, siempre), `hora_pico` (int 0–23 **o `null`**), `antes` (bool **o `null`**). Nada existente se quita.
- Horas en la UI con formato **`HH:00`** (cero-padded, p. ej. `08:00`).
- `construir_tabla_historica(predicciones, observaciones, horas_pico=None, n_dias=20)`; `construir_payload(..., horas_pico=None)`. `horas_pico` es `dict[str, int]` (`fecha -> hora`).
- **Entorno:** ejecutar en clon/worktree local; pytest vía el venv `.venv/Scripts/python.exe -m pytest`. El workflow **Tests** del PR valida la suite completa.
- Commits conventional + trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Spec: `docs/superpowers/specs/2026-06-30-tabla-horas-prediccion-y-pico-design.md`.

---

## File Structure

- `src/sources/wunderground.py` (modificar) — `parse_horas_pico` + `fetch_horas_pico`.
- `src/config.py` (modificar) — `ruta_peak_hours()`.
- `src/storage.py` (modificar) — `read_peak_hours` / `upsert_peak_hours`.
- `src/export.py` (modificar) — `construir_tabla_historica` (3 llaves nuevas) + `construir_payload`.
- `src/predict.py` (modificar) — `_horas_pico_cache` + pasar `horas_pico`.
- `docs/index.html`, `docs/app.js` (modificar) — 3 columnas + scroll horizontal.
- Tests: `tests/test_wunderground.py`, `tests/test_storage.py`, `tests/test_export.py`, `tests/test_predict.py`.

---

## Task 1: `parse_horas_pico` + `fetch_horas_pico` (wunderground)

**Files:**
- Modify: `src/sources/wunderground.py`
- Test: `tests/test_wunderground.py`

**Interfaces:**
- Produces: `parse_horas_pico(payload: dict) -> dict[str, int]` (`fecha_iso -> hora local del máximo`, empate → hora más temprana); `fetch_horas_pico(desde, hasta) -> dict[str, int]` (una llamada de rango a la API).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_wunderground.py`:

```python
def test_parse_horas_pico_hora_del_maximo_por_dia():
    # 1577880000 = 2020-01-01 07:00 Panamá; +3600=08:00; +7200=09:00
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},   # 07:00
        {"valid_time_gmt": 1577883600, "temp": 31.0},   # 08:00  <- máximo
        {"valid_time_gmt": 1577887200, "temp": 30.0},   # 09:00
    ]}
    assert wunderground.parse_horas_pico(payload) == {"2020-01-01": 8}


def test_parse_horas_pico_empate_toma_la_hora_mas_temprana():
    payload = {"observations": [
        {"valid_time_gmt": 1577887200, "temp": 31.0},   # 09:00 (empate, más tarde)
        {"valid_time_gmt": 1577883600, "temp": 31.0},   # 08:00 (empate, más temprano)
    ]}
    assert wunderground.parse_horas_pico(payload) == {"2020-01-01": 8}


def test_parse_horas_pico_ignora_nulos():
    payload = {"observations": [
        {"valid_time_gmt": 1577883600, "temp": None},
        {"valid_time_gmt": 1577887200, "temp": 30.0},   # 09:00
    ]}
    assert wunderground.parse_horas_pico(payload) == {"2020-01-01": 9}
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wunderground.py -k horas_pico -v`
Expected: FAIL (`AttributeError: ... has no attribute 'parse_horas_pico'`).

- [ ] **Step 3: Implementar**

En `src/sources/wunderground.py`, agregar (después de `parse_actual`):

```python
def parse_horas_pico(payload: dict) -> dict:
    """Hora local (Panamá) del máximo de `temp` por día. Empate -> la más temprana."""
    tz = ZoneInfo(config.TZ)
    mejor: dict = {}  # fecha_iso -> (temp_max, hora)
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=tz)
        fecha = dt.date().isoformat()
        prev = mejor.get(fecha)
        if prev is None or temp > prev[0] or (temp == prev[0] and dt.hour < prev[1]):
            mejor[fecha] = (float(temp), dt.hour)
    return {fecha: hora for fecha, (_, hora) in mejor.items()}


def fetch_horas_pico(desde, hasta) -> dict:
    """Hora del pico (local) por día en [desde, hasta]; una sola llamada a la API."""
    api_key = os.environ.get("WUNDERGROUND_API_KEY")
    if not api_key:
        raise RuntimeError("Falta la variable de entorno WUNDERGROUND_API_KEY")
    params = {
        "apiKey": api_key,
        "units": "m",
        "startDate": desde.strftime("%Y%m%d"),
        "endDate": hasta.strftime("%Y%m%d"),
    }
    resp = requests.get(API_URL.format(station=config.ESTACION), params=params,
                        headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_horas_pico(resp.json())
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_wunderground.py -k horas_pico -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sources/wunderground.py tests/test_wunderground.py
git commit -m "feat(wunderground): parse/fetch de la hora del pico por día" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Cache `peak_hours.csv` (config + storage)

**Files:**
- Modify: `src/config.py`, `src/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces: `config.ruta_peak_hours() -> Path` (`data/peak_hours.csv`); `storage.read_peak_hours() -> pd.DataFrame` (cols `fecha, hora_pico`); `storage.upsert_peak_hours(filas: list[dict]) -> None` (dedup por `fecha`, keep last, ordenado).

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_storage.py`:

```python
def test_upsert_y_read_peak_hours(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_peak_hours([{"fecha": "2026-06-20", "hora_pico": 13}])
    storage.upsert_peak_hours([{"fecha": "2026-06-20", "hora_pico": 14},   # reemplaza
                               {"fecha": "2026-06-21", "hora_pico": 15}])
    df = storage.read_peak_hours()
    pares = dict(zip(df["fecha"], df["hora_pico"]))
    assert pares == {"2026-06-20": 14, "2026-06-21": 15}
```

(`tests/test_storage.py` ya importa `from src import storage`; si no, añadir esa importación.)

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/Scripts/python.exe -m pytest tests/test_storage.py -k peak_hours -v`
Expected: FAIL (`AttributeError: ... has no attribute 'upsert_peak_hours'`).

- [ ] **Step 3: Implementar**

En `src/config.py`, agregar (junto a las otras `ruta_*`):

```python
def ruta_peak_hours() -> Path:
    return data_dir() / "peak_hours.csv"
```

En `src/storage.py`, agregar la constante de columnas junto a las otras (`_OBS_COLS = ...`):

```python
_PEAK_COLS = ["fecha", "hora_pico"]
```

y las funciones (después de `upsert_observations`):

```python
def read_peak_hours() -> pd.DataFrame:
    return _read_csv(config.ruta_peak_hours(), _PEAK_COLS)


def upsert_peak_hours(filas: list[dict]) -> None:
    ruta = config.ruta_peak_hours()
    df = pd.concat([read_peak_hours(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates("fecha", keep="last").sort_values("fecha")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
```

- [ ] **Step 4: Correr y verificar que pasa**

Run: `.venv/Scripts/python.exe -m pytest tests/test_storage.py -k peak_hours -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/storage.py tests/test_storage.py
git commit -m "feat(storage): cache peak_hours.csv (hora del pico por día)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `construir_tabla_historica` con horas + ¿antes? (export)

**Files:**
- Modify: `src/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `horas_pico` (`dict[str, int]`).
- Produces: items de `tabla_historica` con `hora_prediccion` (int), `hora_pico` (int|None), `antes` (bool|None); `construir_payload(..., horas_pico=None)`.

- [ ] **Step 1: Actualizar/escribir los tests**

En `tests/test_export.py`, **reemplazar** el cuerpo de `test_tabla_historica_columnas_y_orden` por:

```python
def test_tabla_historica_columnas_y_orden():
    # 2026-06-20: predijo 31 (truncado) desde la hora 6; pico real a las 14 -> antes.
    # 2026-06-21: predijo 33 solo en la final (16); pico a las 13 -> NO antes.
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 6,  "pico_pred": 31.2, "p10": 30, "p90": 33, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-20", "hora_decision": 16, "pico_pred": 31.6, "p10": 30, "p90": 33, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-21", "hora_decision": 16, "pico_pred": 33.2, "p10": 32, "p90": 34, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([
        {"fecha": "2026-06-20", "temp_max_c": 33.0},
        {"fecha": "2026-06-21", "temp_max_c": 33.0},
    ])
    horas_pico = {"2026-06-20": 14, "2026-06-21": 13}
    out = export.construir_tabla_historica(predicciones, observaciones, horas_pico)
    assert [r["fecha"] for r in out] == ["2026-06-21", "2026-06-20"]
    assert out[0] == {"fecha": "2026-06-21", "prediccion": 33, "real": 33,
                      "hora_prediccion": 16, "hora_pico": 13, "antes": False,
                      "se_cumplio": True, "tasa_error_pct": 0.0, "diferencia": 0}
    assert out[1] == {"fecha": "2026-06-20", "prediccion": 31, "real": 33,
                      "hora_prediccion": 6, "hora_pico": 14, "antes": True,
                      "se_cumplio": False, "tasa_error_pct": 6.1, "diferencia": -2}
```

**Reemplazar** el cuerpo de `test_tabla_historica_trunca_no_redondea` por:

```python
def test_tabla_historica_trunca_no_redondea():
    # 32.9 se TRUNCA a 32 (no 33). Sin horas_pico -> hora_pico/antes = None.
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-19", "hora_decision": 16,
         "pico_pred": 32.9, "p10": 32, "p90": 33, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-19", "temp_max_c": 33.0}])
    out = export.construir_tabla_historica(predicciones, observaciones)
    assert out[0] == {"fecha": "2026-06-19", "prediccion": 32, "real": 33,
                      "hora_prediccion": 16, "hora_pico": None, "antes": None,
                      "se_cumplio": False, "tasa_error_pct": 3.0, "diferencia": -1}
```

**Agregar** un test de la "primera hora que fijó el valor":

```python
def test_tabla_historica_hora_prediccion_primera_coincidencia():
    # Predijo 31 a la hora 6, bajó a 30 a la 10, volvió a 31 en la final (16).
    # hora_prediccion = 6 (primera vez que el truncado fue el final).
    predicciones = pd.DataFrame([
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 6,  "pico_pred": 31.0, "p10": 30, "p90": 32, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 10, "pico_pred": 30.0, "p10": 29, "p90": 31, "modelo_version": "v"},
        {"run_timestamp": "x", "fecha_objetivo": "2026-06-22", "hora_decision": 16, "pico_pred": 31.0, "p10": 30, "p90": 32, "modelo_version": "v"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-22", "temp_max_c": 31.0}])
    out = export.construir_tabla_historica(predicciones, observaciones)
    assert out[0]["hora_prediccion"] == 6
    assert out[0]["se_cumplio"] is True
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py -k tabla_historica -v`
Expected: FAIL (las llaves nuevas no existen / `construir_tabla_historica` no acepta `horas_pico`).

- [ ] **Step 3: Implementar**

En `src/export.py`, **reemplazar** `construir_tabla_historica` por:

```python
def construir_tabla_historica(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                              horas_pico: dict | None = None,
                              n_dias: int = 20) -> list[dict]:
    """Registro por día (predicción final vs pico real) de los últimos `n_dias`
    días con pico real, más reciente primero. Incluye la hora en que el modelo
    fijó su valor y la hora del pico real (si está en `horas_pico`).
    """
    if len(predicciones) == 0 or len(observaciones) == 0:
        return []
    horas_pico = horas_pico or {}
    real = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for fecha, grupo in predicciones.groupby("fecha_objetivo"):
        if fecha not in real:
            continue
        g = grupo.sort_values("hora_decision")
        pred = int(float(g.iloc[-1]["pico_pred"]))   # truncado a grados enteros
        r = int(float(real[fecha]))
        match = g[g["pico_pred"].astype(int) == pred]
        hora_prediccion = int(match.iloc[0]["hora_decision"])
        hp = horas_pico.get(fecha)
        hora_pico = int(hp) if hp is not None else None
        antes = (hora_prediccion < hora_pico) if hora_pico is not None else None
        filas.append({
            "fecha": fecha,
            "prediccion": pred,
            "real": r,
            "hora_prediccion": hora_prediccion,
            "hora_pico": hora_pico,
            "antes": antes,
            "se_cumplio": pred == r,
            "tasa_error_pct": round(abs(pred - r) / r * 100, 1),
            "diferencia": pred - r,
        })
    filas.sort(key=lambda x: x["fecha"], reverse=True)
    return filas[:n_dias]
```

En `construir_payload`, cambiar la firma para aceptar `horas_pico` y pasarlo:

```python
def construir_payload(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                      evaluacion: pd.DataFrame, hoy: str,
                      curva_hoy: list | None = None,
                      generado: str | None = None,
                      temp_actual: dict | None = None,
                      horas_pico: dict | None = None) -> dict:
```

y en el `return {...}` reemplazar la línea de `tabla_historica` por:

```python
        "tabla_historica": construir_tabla_historica(predicciones, observaciones, horas_pico),
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py -v`
Expected: PASS (toda la suite de export).

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat(export): tabla con hora de predicción, hora del pico y ¿antes?" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Llenado del cache en `predict.py`

**Files:**
- Modify: `src/predict.py`
- Test: `tests/test_predict.py`

**Interfaces:**
- Consumes: `wunderground.fetch_horas_pico` (Task 1), `storage.read_peak_hours`/`upsert_peak_hours` (Task 2), `construir_payload(..., horas_pico=...)` (Task 3).
- Produces: `predict._horas_pico_cache(observaciones, dias=25) -> dict[str, int]`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_predict.py` (añadir al tope `import pandas as pd` y `from src import predict, storage` si no están):

```python
def test_horas_pico_cache_rellena_faltantes(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(predict.wunderground, "fetch_horas_pico",
                        lambda desde, hasta: {"2026-06-20": 13, "2026-06-21": 14})
    obs = pd.DataFrame([{"fecha": "2026-06-20", "temp_max_c": 33.0},
                        {"fecha": "2026-06-21", "temp_max_c": 32.0}])
    out = predict._horas_pico_cache(obs)
    assert out == {"2026-06-20": 13, "2026-06-21": 14}
    assert set(storage.read_peak_hours()["fecha"]) == {"2026-06-20", "2026-06-21"}


def test_horas_pico_cache_no_refetch_si_ya_esta(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_peak_hours([{"fecha": "2026-06-20", "hora_pico": 13}])

    def boom(*a, **k):
        raise AssertionError("no debería llamar a la API si ya está cacheado")

    monkeypatch.setattr(predict.wunderground, "fetch_horas_pico", boom)
    obs = pd.DataFrame([{"fecha": "2026-06-20", "temp_max_c": 33.0}])
    assert predict._horas_pico_cache(obs) == {"2026-06-20": 13}
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_predict.py -k horas_pico -v`
Expected: FAIL (`AttributeError: module 'src.predict' has no attribute '_horas_pico_cache'`).

- [ ] **Step 3: Implementar**

En `src/predict.py`, agregar la función (después de `_temp_actual_mpmg`):

```python
def _horas_pico_cache(observaciones: pd.DataFrame, dias: int = 25) -> dict:
    """Rellena (lazy) y devuelve el cache fecha->hora_pico de los últimos `dias`
    días observados. Una sola llamada de rango a Wunderground para los faltantes;
    si falla, deja el cache como está (se reintenta la próxima corrida).
    """
    cache = storage.read_peak_hours()
    conocidas = set(cache["fecha"].astype(str))
    recientes = [str(f) for f in observaciones.tail(dias)["fecha"]]
    faltantes = sorted(f for f in recientes if f not in conocidas)
    if faltantes:
        try:
            nuevas = wunderground.fetch_horas_pico(
                date.fromisoformat(faltantes[0]), date.fromisoformat(faltantes[-1]))
            faltantes_set = set(faltantes)
            filas = [{"fecha": f, "hora_pico": int(h)}
                     for f, h in nuevas.items() if f in faltantes_set]
            if filas:
                storage.upsert_peak_hours(filas)
                cache = storage.read_peak_hours()
        except Exception:
            pass
    return {str(r["fecha"]): int(r["hora_pico"]) for _, r in cache.iterrows()}
```

Y en `correr`, justo después de `temp_actual = _temp_actual_mpmg(hoy)` (antes de construir el payload), agregar:

```python
    horas_pico = _horas_pico_cache(observaciones)
```

y cambiar la llamada a `construir_payload` para pasar `horas_pico=horas_pico`:

```python
    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy=hoy.isoformat(),
                                       curva_hoy=curva, temp_actual=temp_actual,
                                       horas_pico=horas_pico)
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/Scripts/python.exe -m pytest tests/test_predict.py -k horas_pico -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/predict.py tests/test_predict.py
git commit -m "feat(predict): rellena el cache de horas del pico y lo pasa al payload" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Frontend — 3 columnas nuevas + scroll horizontal

**Files:**
- Modify: `docs/index.html`, `docs/app.js`

**Interfaces:**
- Consumes: items de `tabla_historica` con `hora_prediccion`, `hora_pico`, `antes`.

- [ ] **Step 1: `index.html` — encabezados, scroll y estilo**

En `docs/index.html`, **reemplazar** el bloque de la tabla (desde `<table id="tabla-historica">` hasta `</table>`) por:

```html
  <div class="tabla-scroll">
  <table id="tabla-historica">
    <thead>
      <tr><th>Día</th><th>Predicción</th><th>Hora pred.</th><th>Pico Real</th><th>Hora pico</th><th>¿Antes?</th><th>Se cumplió</th><th>Tasa de error</th><th>Diferencia</th></tr>
    </thead>
    <tbody id="tabla-historica-body"></tbody>
  </table>
  </div>
```

En el `<style>`, agregar (junto a las reglas de `#tabla-historica`):

```css
    .tabla-scroll { overflow-x: auto; }
    #tabla-historica { min-width: 640px; }
```

- [ ] **Step 2: `app.js` — pintar las celdas nuevas**

En `docs/app.js`, **reemplazar** la función `renderTablaHistorica` por:

```js
function renderTablaHistorica(arr) {
  const body = document.getElementById('tabla-historica-body');
  const nota = document.getElementById('tabla-nota');
  const tabla = document.getElementById('tabla-historica');
  if (!arr.length) { body.innerHTML = ''; tabla.hidden = true; nota.hidden = false; return; }
  tabla.hidden = false; nota.hidden = true;
  const hhmm = (h) => (h == null ? '—' : String(h).padStart(2, '0') + ':00');
  body.innerHTML = arr.map(r => {
    const dif = (r.diferencia >= 0 ? '+' : '') + r.diferencia;
    const cumplio = r.se_cumplio
      ? '<span class="si">✓ Sí</span>'
      : '<span class="no">✗ No</span>';
    const antes = r.antes === true ? '<span class="si">✓</span>'
                : r.antes === false ? '<span class="no">✗</span>'
                : '—';
    return `<tr>
      <td>${r.fecha.slice(5)}</td>
      <td>${r.prediccion}°C</td>
      <td>${hhmm(r.hora_prediccion)}</td>
      <td>${r.real}°C</td>
      <td>${hhmm(r.hora_pico)}</td>
      <td>${antes}</td>
      <td>${cumplio}</td>
      <td>${r.tasa_error_pct.toFixed(1)}%</td>
      <td>${dif}°C</td>
    </tr>`;
  }).join('');
}
```

- [ ] **Step 3: Verificación visual**

`python -m http.server -d docs 8000` → abrir `http://localhost:8000`. Con el `data.json` actual (sin los campos nuevos) las celdas Hora pico/¿Antes? muestran "—" y nada se rompe. Probar en consola:
`renderTablaHistorica([{fecha:'2026-06-20',prediccion:31,real:33,hora_prediccion:6,hora_pico:14,antes:true,se_cumplio:false,tasa_error_pct:6.1,diferencia:-2},{fecha:'2026-06-21',prediccion:33,real:33,hora_prediccion:16,hora_pico:13,antes:false,se_cumplio:true,tasa_error_pct:0.0,diferencia:0}])`
→ "06:00"/"14:00", "¿Antes?" ✓ verde / ✗ rojo; en pantalla angosta la tabla hace scroll horizontal.

- [ ] **Step 4: Commit**

```bash
git add docs/index.html docs/app.js
git commit -m "feat(dashboard): columnas hora de predicción, hora del pico y ¿antes? en la tabla" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verificación final

- [ ] `.venv/Scripts/python.exe -m pytest -v` en verde (o el workflow **Tests** del PR).
- [ ] Servir `docs/` y revisar las 3 columnas + scroll horizontal; confirmar que el `data.json` viejo no rompe nada.
- [ ] Abrir PR a `main`. Tras el merge, la primera corrida de `hourly.yml` rellena `data/peak_hours.csv` (backfill lazy de ~20 días) y regenera `data.json` con las horas.

## Notas

- Orden: Task 1 → 2 → 3 → 4 (backend) → 5 (frontend). 3 depende de nada de 1/2 (solo recibe `horas_pico`); 4 depende de 1, 2 y 3.
- `predict.py` ya importa `date` y `wunderground`; `hourly.yml` ya hace `git add data/`. Sin cambios de workflow.
