# Mejora del modelo con datos MPMG — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el modelo de pico use la curva real de la estación MPMG (regla dura + features), con backtest reproducible e intervalos calibrados.

**Architecture:** Tres fases desplegables por separado: (A) piso `max(pred, max_observado_mpmg)` en `predict.py`; (B) nueva serie `data/mpmg_hourly.csv` (Weather.com API por rangos mensuales) que alimenta dos features nuevas; (C) `src/backtest.py` rolling-origin mensual y calibración conformal (CQR) del intervalo p10–p90 con `q_hat` persistido en el archivo del modelo.

**Tech Stack:** Python 3.12, pandas, LightGBM (cuantiles), pytest con fixtures/mocks (`unittest.mock.patch`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-07-03-mejora-modelo-mpmg-design.md`

## Global Constraints

- Código y docstrings en español, mismo estilo del repo (módulos chicos, funciones `_privadas`, comentarios que explican el porqué).
- Si la API de Wunderground falla, TODO degrada al comportamiento actual (nunca rompe la corrida).
- `MODELO_VERSION` pasa a `"gbm-q-v2"` solo en la Tarea 5 (cuando cambia el contrato de features).
- `ModeloPico.cargar` debe seguir leyendo el archivo v1 (sin clave `calibracion`).
- Tests con `PTF_DATA_DIR`/`PTF_MODEL_DIR` → `tmp_path` (patrón existente).
- Sin dependencias nuevas.

---

### Task 1: Fase A — piso MPMG en la predicción

**Files:**
- Modify: `src/predict.py`
- Test: `tests/test_predict.py`

**Interfaces:**
- Produces: `predict._aplicar_piso(p10, p50, p90, curva) -> tuple[float, float, float]`; en `correr`, la curva MPMG se descarga ANTES de predecir y se reutiliza para el dashboard (variable `curva_mpmg`).

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_predict.py`:

```python
def test_prediccion_no_baja_del_maximo_observado_mpmg(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(predict, "RUTA_DATA_JSON", tmp_path / "data.json")
    _sembrar_y_entrenar()

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    # La estación ya registró 36.0 °C a las 10; el modelo (entrenado ~32) queda por debajo.
    wu_curva = [{"hora": h, "temp_c": 26.0 + h} for h in range(16)]
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict.wunderground.fetch_curva_intradia", return_value=wu_curva), \
         patch("src.predict.wunderground.fetch_actual", return_value=None), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    fila = storage.read_predictions().iloc[0]
    # El máximo ya observado hasta las 10 es 36.0: ningún cuantil puede quedar debajo.
    assert fila["p10"] >= 36.0
    assert fila["pico_pred"] >= 36.0
    assert fila["p90"] >= 36.0


def test_sin_curva_mpmg_no_se_aplica_piso(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(predict, "RUTA_DATA_JSON", tmp_path / "data.json")
    _sembrar_y_entrenar()

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict.wunderground.fetch_curva_intradia",
               side_effect=RuntimeError("sin key")), \
         patch("src.predict.wunderground.fetch_actual",
               side_effect=RuntimeError("sin key")), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    fila = storage.read_predictions().iloc[0]
    # Sin estación disponible la predicción queda como la dé el modelo (~32, no 36).
    assert fila["pico_pred"] < 36.0
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/test_predict.py -k "piso or maximo_observado" -v`
Expected: FAIL (`pico_pred` ~31-33 < 36.0 en el primero; el segundo puede pasar ya — se mantiene como regresión).

- [ ] **Step 3: Implementar el piso en `src/predict.py`**

Añadir la función (después de `_temp_actual_mpmg`):

```python
def _aplicar_piso(p10: float, p50: float, p90: float,
                  curva: list[dict] | None) -> tuple[float, float, float]:
    """El pico del día nunca puede ser menor que el máximo ya observado en MPMG.

    Corrige la incoherencia de predecir por debajo de una temperatura que la
    estación ya registró. Sin curva (API caída) no se aplica nada.
    """
    if not curva:
        return p10, p50, p90
    piso = max(c["temp_c"] for c in curva)
    return max(p10, piso), max(p50, piso), max(p90, piso)
```

En `correr`, mover la descarga de la curva ANTES de la predicción y aplicar el piso.
Reemplazar el bloque del paso 3 actual:

```python
    # 3. Curva real de MPMG: se usa como piso de la predicción y en el dashboard.
    curva_mpmg = _curva_observada_mpmg(hoy, hora)

    # 4. Features y predicción.
    fila = features.construir_fila(intradia, fecha=hoy.isoformat(),
                                   hora_h=hora, forecast_max=forecast_max)
    modelo = ModeloPico.cargar(config.ruta_modelo())
    p10, p50, p90 = modelo.predecir(fila)
    p10, p50, p90 = _aplicar_piso(p10, p50, p90, curva_mpmg)
```

Y más abajo, donde hoy se llama `_curva_observada_mpmg`, reutilizar `curva_mpmg`:

```python
    curva = curva_mpmg
    if curva is None:
        curva = _curva_observada(intradia, hora)
```

(Renumerar los comentarios de pasos que siguen.)

- [ ] **Step 4: Correr la suite del módulo**

Run: `python -m pytest tests/test_predict.py -v`
Expected: PASS (todos, incluidos los existentes).

- [ ] **Step 5: Commit**

```bash
git add src/predict.py tests/test_predict.py
git commit -m "feat: la predicción nunca baja del máximo ya observado en MPMG"
```

---

### Task 2: Storage y config para `mpmg_hourly.csv`

**Files:**
- Modify: `src/config.py`, `src/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces: `config.ruta_mpmg_horario() -> Path`; `storage.read_mpmg_hourly() -> pd.DataFrame` (cols `fecha,hora,temp_c`); `storage.upsert_mpmg_hourly(filas: list[dict]) -> None` (upsert por `(fecha, hora)`).

- [ ] **Step 1: Test que falla**

Añadir a `tests/test_storage.py`:

```python
def test_upsert_mpmg_hourly_dedup_por_fecha_hora(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_mpmg_hourly([
        {"fecha": "2026-06-16", "hora": 10, "temp_c": 30.0},
        {"fecha": "2026-06-16", "hora": 11, "temp_c": 31.0},
    ])
    storage.upsert_mpmg_hourly([
        {"fecha": "2026-06-16", "hora": 11, "temp_c": 31.5},  # pisa la anterior
        {"fecha": "2026-06-17", "hora": 9, "temp_c": 29.0},
    ])
    df = storage.read_mpmg_hourly()
    assert len(df) == 3
    fila_11 = df[(df["fecha"] == "2026-06-16") & (df["hora"] == 11)].iloc[0]
    assert fila_11["temp_c"] == 31.5
    assert list(df.columns) == ["fecha", "hora", "temp_c"]
```

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/test_storage.py -k mpmg -v`
Expected: FAIL con `AttributeError: ... 'upsert_mpmg_hourly'`

- [ ] **Step 3: Implementar**

En `src/config.py` (junto a las otras rutas):

```python
def ruta_mpmg_horario() -> Path:
    return data_dir() / "mpmg_hourly.csv"
```

En `src/storage.py` (constante junto a las demás; funciones junto a las de hourly):

```python
_MPMG_COLS = ["fecha", "hora", "temp_c"]


def read_mpmg_hourly() -> pd.DataFrame:
    return _read_csv(config.ruta_mpmg_horario(), _MPMG_COLS)


def upsert_mpmg_hourly(filas: list[dict]) -> None:
    ruta = config.ruta_mpmg_horario()
    df = pd.concat([read_mpmg_hourly(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates(["fecha", "hora"], keep="last") \
        .sort_values(["fecha", "hora"])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/storage.py tests/test_storage.py
git commit -m "feat: storage para el horario de la estación MPMG (mpmg_hourly.csv)"
```

---

### Task 3: Wunderground — horario por rango de fechas

**Files:**
- Modify: `src/sources/wunderground.py`
- Test: `tests/test_wunderground.py`

**Interfaces:**
- Consumes: endpoint `observations/historical.json` (mismo de `fetch_horas_pico`, acepta rangos).
- Produces: `wunderground.parse_horario_rango(payload: dict) -> list[dict]` (filas `{"fecha", "hora", "temp_c"}`, máximo por hora local); `wunderground.fetch_horario_rango(desde: date, hasta: date) -> list[dict]`.

- [ ] **Step 1: Test que falla**

Añadir a `tests/test_wunderground.py` (usar el estilo de payload de los tests existentes de `parse_horas_pico`/`parse_curva_intradia`; los timestamps son epoch UTC y Panamá es UTC-5):

```python
def test_parse_horario_rango_agrupa_por_fecha_y_hora():
    # 2026-06-16 10:00 local = 15:00 UTC = 1781622000
    payload = {"observations": [
        {"valid_time_gmt": 1781622000, "temp": 30.0},   # 16/6 10:00 local
        {"valid_time_gmt": 1781623800, "temp": 30.6},   # 16/6 10:30 → máx de la hora 10
        {"valid_time_gmt": 1781625600, "temp": 31.2},   # 16/6 11:00
        {"valid_time_gmt": 1781708400, "temp": 29.0},   # 17/6 10:00
        {"valid_time_gmt": 1781626000, "temp": None},   # sin temp: se ignora
    ]}
    filas = wunderground.parse_horario_rango(payload)
    assert filas == [
        {"fecha": "2026-06-16", "hora": 10, "temp_c": 30.6},
        {"fecha": "2026-06-16", "hora": 11, "temp_c": 31.2},
        {"fecha": "2026-06-17", "hora": 10, "temp_c": 29.0},
    ]
```

(Verificar los epochs con `datetime.fromtimestamp(ts, ZoneInfo("America/Panama"))`
al escribir el test; ajustarlos si el cálculo de arriba no cuadra.)

- [ ] **Step 2: Verificar que falla**

Run: `python -m pytest tests/test_wunderground.py -k horario_rango -v`
Expected: FAIL con `AttributeError`

- [ ] **Step 3: Implementar**

En `src/sources/wunderground.py`, después de `parse_horas_pico`/`fetch_horas_pico`:

```python
def parse_horario_rango(payload: dict) -> list[dict]:
    """Máximo de `temp` por (fecha, hora) local de Panamá para todo el payload.

    Es la versión multi-día de `parse_curva_intradia`: alimenta el histórico
    horario de la estación (mpmg_hourly.csv) que usan las features del modelo.
    """
    tz = ZoneInfo(config.TZ)
    por_clave: dict[tuple[str, int], float] = {}
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=tz)
        clave = (dt.date().isoformat(), dt.hour)
        if clave not in por_clave or temp > por_clave[clave]:
            por_clave[clave] = float(temp)
    return [{"fecha": f, "hora": h, "temp_c": round(t, 1)}
            for (f, h), t in sorted(por_clave.items())]


def fetch_horario_rango(desde, hasta) -> list[dict]:
    """Horario observado de MPMG en [desde, hasta]; una sola llamada a la API."""
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
    return parse_horario_rango(resp.json())
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/test_wunderground.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sources/wunderground.py tests/test_wunderground.py
git commit -m "feat: fetch del horario MPMG por rango de fechas"
```

---

### Task 4: Backfill y actualización diaria del horario MPMG

**Files:**
- Modify: `src/backfill.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `wunderground.fetch_horario_rango`, `storage.upsert_mpmg_hourly` (Tareas 2–3).
- Produces: `backfill._backfill_mpmg_horario(desde: date, hasta: date) -> None` (mes a mes, tolerante a fallos); `backfill.correr` gana el paso 3; `backfill.actualizar_reciente` refresca también MPMG.

- [ ] **Step 1: Tests que fallan**

Añadir a `tests/test_backfill.py`:

```python
def test_backfill_mpmg_horario_mensual_tolera_fallos(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    llamadas = []

    def fake_fetch(desde, hasta):
        llamadas.append((desde.isoformat(), hasta.isoformat()))
        if desde.month == 2:
            raise RuntimeError("mes sin cobertura")
        return [{"fecha": desde.isoformat(), "hora": 13, "temp_c": 31.0}]

    monkeypatch.setattr(backfill.wunderground, "fetch_horario_rango", fake_fetch)
    backfill._backfill_mpmg_horario(date(2026, 1, 15), date(2026, 3, 10))

    # Tres bloques mensuales: 15/1-31/1, 1/2-28/2 (falla y no interrumpe), 1/3-10/3.
    assert llamadas == [("2026-01-15", "2026-01-31"),
                        ("2026-02-01", "2026-02-28"),
                        ("2026-03-01", "2026-03-10")]
    df = storage.read_mpmg_hourly()
    assert set(df["fecha"]) == {"2026-01-15", "2026-03-01"}


def test_actualizar_reciente_refresca_mpmg(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(backfill.openmeteo, "fetch_archivo", lambda d, h: [])
    monkeypatch.setattr(backfill, "_backfill_forecast", lambda d, h: None)
    monkeypatch.setattr(backfill.wunderground, "fetch_via_api",
                        lambda d, h: [])
    monkeypatch.setattr(backfill.wunderground, "fetch_horario_rango",
                        lambda d, h: [{"fecha": "2026-06-16", "hora": 12,
                                       "temp_c": 32.0}])
    backfill.actualizar_reciente(dias=3)
    df = storage.read_mpmg_hourly()
    assert len(df) == 1
    assert df.iloc[0]["temp_c"] == 32.0
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/test_backfill.py -k mpmg -v`
Expected: FAIL con `AttributeError: ... '_backfill_mpmg_horario'` y sin datos en el segundo.

- [ ] **Step 3: Implementar en `src/backfill.py`**

Después de `_corregir_con_wunderground`:

```python
def _backfill_mpmg_horario(desde: date, hasta: date) -> None:
    """Llena mpmg_hourly.csv con el horario real de la estación, mes a mes.

    Alimenta las features intradía del modelo (temp_actual_mpmg,
    max_hasta_ahora_mpmg). Un mes que falle (límite de tasa, hueco de la
    estación) se omite con aviso y no interrumpe el resto; re-ejecutar el
    backfill lo completa porque el guardado es upsert por (fecha, hora).
    """
    cursor = desde
    while cursor <= hasta:
        ultimo_dia = calendar.monthrange(cursor.year, cursor.month)[1]
        fin_mes = min(date(cursor.year, cursor.month, ultimo_dia), hasta)
        try:
            filas = wunderground.fetch_horario_rango(cursor, fin_mes)
            if filas:
                storage.upsert_mpmg_hourly(filas)
                print(f"  MPMG horario {cursor}..{fin_mes}: {len(filas)} filas")
        except Exception as e:
            print(f"  MPMG horario {cursor}..{fin_mes}: sin datos ({e})")
        cursor = fin_mes + timedelta(days=1)
```

En `correr`, después de `_corregir_con_wunderground(desde, hasta)`:

```python
    print("Descargando horario real de MPMG…")
    _backfill_mpmg_horario(desde, hasta)
```

En `actualizar_reciente`, al final (después del bloque `fetch_via_api`):

```python
    try:
        filas_mpmg = wunderground.fetch_horario_rango(desde, hasta)
        if filas_mpmg:
            storage.upsert_mpmg_hourly(filas_mpmg)
    except Exception:
        pass  # sin API las features MPMG de esos días quedan NaN
```

- [ ] **Step 4: Verificar suite del módulo**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backfill.py tests/test_backfill.py
git commit -m "feat: backfill y refresco diario del horario MPMG"
```

---

### Task 5: Features MPMG en features/dataset/train/predict (modelo v2)

**Files:**
- Modify: `src/features.py`, `src/dataset.py`, `src/train.py`, `src/predict.py`, `src/config.py`
- Test: `tests/test_features.py`, `tests/test_dataset.py`

**Interfaces:**
- Consumes: `storage.read_mpmg_hourly()` (Tarea 2); en predict, la variable `curva_mpmg` (Tarea 1, misma forma `[{"hora", "temp_c"}]`).
- Produces: `FEATURE_COLS` + `["temp_actual_mpmg", "max_hasta_ahora_mpmg"]`; `features.construir_fila(..., mpmg_intradia: list[dict] | None = None)`; `dataset.construir_set(..., mpmg_horario: pd.DataFrame | None = None)`; `config.MODELO_VERSION = "gbm-q-v2"`.

- [ ] **Step 1: Tests que fallan**

Añadir a `tests/test_features.py`:

```python
def test_features_mpmg_presentes():
    intradia = pd.DataFrame([
        {"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24.0 + h,
         "humedad": 80.0, "nubosidad": 30.0} for h in range(12)])
    mpmg = [{"hora": 8, "temp_c": 28.5}, {"hora": 9, "temp_c": 30.1},
            {"hora": 10, "temp_c": 31.4}, {"hora": 12, "temp_c": 33.0}]
    fila = features.construir_fila(intradia, fecha="2026-06-16", hora_h=10,
                                   forecast_max=32.0, mpmg_intradia=mpmg)
    # Solo cuenta lo observado hasta la hora de decisión (10): la hora 12 no.
    assert fila["temp_actual_mpmg"] == 31.4
    assert fila["max_hasta_ahora_mpmg"] == 31.4


def test_features_mpmg_usa_ultima_hora_disponible():
    intradia = pd.DataFrame([
        {"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24.0 + h,
         "humedad": 80.0, "nubosidad": 30.0} for h in range(12)])
    # La estación va atrasada: su última hora es 9 aunque decidimos a las 11.
    mpmg = [{"hora": 8, "temp_c": 31.0}, {"hora": 9, "temp_c": 29.5}]
    fila = features.construir_fila(intradia, fecha="2026-06-16", hora_h=11,
                                   forecast_max=32.0, mpmg_intradia=mpmg)
    assert fila["temp_actual_mpmg"] == 29.5      # última disponible ≤ 11
    assert fila["max_hasta_ahora_mpmg"] == 31.0  # máximo hasta las 11


def test_features_mpmg_none_sin_datos():
    intradia = pd.DataFrame([
        {"timestamp": "2026-06-16T08:00", "temp_c": 27.0,
         "humedad": 80.0, "nubosidad": 30.0}])
    fila = features.construir_fila(intradia, fecha="2026-06-16", hora_h=8,
                                   forecast_max=None)
    assert fila["temp_actual_mpmg"] is None
    assert fila["max_hasta_ahora_mpmg"] is None
    assert "temp_actual_mpmg" in features.FEATURE_COLS
    assert "max_hasta_ahora_mpmg" in features.FEATURE_COLS
```

Añadir a `tests/test_dataset.py`:

```python
def test_construir_set_incluye_features_mpmg():
    hist = pd.DataFrame([
        {"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24.0 + h,
         "humedad": 80.0, "nubosidad": 30.0} for h in range(17)])
    obs = pd.DataFrame([{"fecha": "2026-06-16", "temp_max_c": 33.5}])
    mpmg = pd.DataFrame([{"fecha": "2026-06-16", "hora": 9, "temp_c": 30.2},
                         {"fecha": "2026-06-16", "hora": 10, "temp_c": 31.8}])
    set_ent = dataset.construir_set(hist, obs, {}, mpmg_horario=mpmg)
    fila_10 = set_ent[set_ent["hora_decision"] == 10].iloc[0]
    assert fila_10["max_hasta_ahora_mpmg"] == 31.8
    fila_6 = set_ent[set_ent["hora_decision"] == 6].iloc[0]
    assert pd.isna(fila_6["max_hasta_ahora_mpmg"]) or \
        fila_6["max_hasta_ahora_mpmg"] is None
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/test_features.py tests/test_dataset.py -k mpmg -v`
Expected: FAIL (`construir_fila` no acepta `mpmg_intradia`; faltan claves).

- [ ] **Step 3: Implementar**

`src/features.py` — ampliar `FEATURE_COLS` y `construir_fila`:

```python
FEATURE_COLS = [
    "hora_decision", "doy_sin", "doy_cos", "mes",
    "max_hasta_ahora", "temp_actual", "temp_lag1", "temp_lag2", "temp_lag3",
    "tasa_subida", "humedad_actual", "nubosidad_actual", "forecast_max",
    "temp_actual_mpmg", "max_hasta_ahora_mpmg",
]
```

Firma: `def construir_fila(intradia, fecha, hora_h, forecast_max, mpmg_intradia: list[dict] | None = None) -> dict:`

Antes del `return`, calcular:

```python
    # Curva real de la estación (fuente del target): solo horas <= hora_h.
    # La estación puede ir atrasada; "actual" = última hora disponible.
    mpmg_hasta = sorted((c for c in (mpmg_intradia or [])
                         if c["hora"] <= hora_h), key=lambda c: c["hora"])
    temp_actual_mpmg = float(mpmg_hasta[-1]["temp_c"]) if mpmg_hasta else None
    max_mpmg = max((float(c["temp_c"]) for c in mpmg_hasta), default=None)
```

Y en el dict devuelto añadir:

```python
        "temp_actual_mpmg": temp_actual_mpmg,
        "max_hasta_ahora_mpmg": max_mpmg,
```

`src/dataset.py` — firma `construir_set(hist_horario, observaciones, forecast_por_fecha=None, mpmg_horario=None)`; antes del loop:

```python
    mpmg_por_fecha: dict[str, list[dict]] = {}
    if mpmg_horario is not None and len(mpmg_horario):
        for f, g in mpmg_horario.groupby("fecha"):
            mpmg_por_fecha[str(f)] = [
                {"hora": int(r["hora"]), "temp_c": float(r["temp_c"])}
                for _, r in g.iterrows()]
```

y en la llamada a `construir_fila` añadir `mpmg_intradia=mpmg_por_fecha.get(fecha)`.

`src/train.py` — en `correr`, leer y pasar el horario MPMG:

```python
    mpmg = storage.read_mpmg_hourly()
    set_ent = dataset.construir_set(hist, obs, forecast_por_fecha, mpmg_horario=mpmg)
```

`src/predict.py` — pasar la curva ya descargada (Tarea 1):

```python
    fila = features.construir_fila(intradia, fecha=hoy.isoformat(),
                                   hora_h=hora, forecast_max=forecast_max,
                                   mpmg_intradia=curva_mpmg)
```

`src/config.py`:

```python
MODELO_VERSION = "gbm-q-v2"
```

- [ ] **Step 4: Correr toda la suite**

Run: `python -m pytest -q`
Expected: PASS completo (el modelo tolera las columnas nuevas como NaN; si algún test fijaba `MODELO_VERSION`, actualizarlo a `gbm-q-v2`).

- [ ] **Step 5: Commit**

```bash
git add src/features.py src/dataset.py src/train.py src/predict.py src/config.py tests/test_features.py tests/test_dataset.py
git commit -m "feat: features intradía de la estación MPMG (modelo gbm-q-v2)"
```

---

### Task 6: Calibración conformal del intervalo (CQR)

**Files:**
- Modify: `src/model.py`, `src/train.py`
- Test: `tests/test_model.py`, `tests/test_train.py`

**Interfaces:**
- Produces: `ModeloPico.q_hat: float` (default 0.0); `predecir` devuelve intervalo `[p10 - q_hat, p90 + q_hat]` (p50 igual); `guardar/cargar` persisten `{"calibracion": {"q_hat": ...}}` y toleran su ausencia; `model.entrenar_calibrado(set_ent: pd.DataFrame, dias_calibracion: int = 45) -> ModeloPico`.

- [ ] **Step 1: Tests que fallan**

Añadir a `tests/test_model.py` (reusar el helper de dataset sintético del archivo si existe; si no, este):

```python
def _set_sintetico(n_dias=80, seed=7):
    rng = np.random.default_rng(seed)
    filas = []
    base = pd.Timestamp("2025-01-01")
    for d in range(n_dias):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in range(6, 17):
            filas.append({"fecha_objetivo": fecha, "hora_decision": h,
                          "doy_sin": 0.5, "doy_cos": 0.5, "mes": 1,
                          "max_hasta_ahora": pico - 2, "temp_actual": pico - 2,
                          "temp_lag1": pico - 3, "temp_lag2": pico - 4,
                          "temp_lag3": pico - 5, "tasa_subida": 1.0,
                          "humedad_actual": 80.0, "nubosidad_actual": 30.0,
                          "forecast_max": pico + rng.normal(0, 0.5),
                          "temp_actual_mpmg": pico - 2,
                          "max_hasta_ahora_mpmg": pico - 2,
                          "target": pico})
    return pd.DataFrame(filas)


def test_q_hat_ensancha_el_intervalo():
    set_ent = _set_sintetico()
    m = ModeloPico().ajustar(set_ent)
    fila = set_ent.iloc[0].to_dict()
    p10_a, p50_a, p90_a = m.predecir(fila)
    m.q_hat = 0.7
    p10_b, p50_b, p90_b = m.predecir(fila)
    assert p10_b == round(p10_a - 0.7, 1)
    assert p90_b == round(p90_a + 0.7, 1)
    assert p50_b == p50_a


def test_guardar_cargar_persiste_q_hat(tmp_path):
    set_ent = _set_sintetico()
    m = ModeloPico().ajustar(set_ent)
    m.q_hat = 0.4
    m.guardar(tmp_path / "modelo.txt")
    m2 = ModeloPico.cargar(tmp_path / "modelo.txt")
    assert m2.q_hat == 0.4


def test_cargar_modelo_v1_sin_calibracion(tmp_path):
    # Un archivo v1 solo trae los tres boosters; q_hat debe quedar en 0.
    set_ent = _set_sintetico()
    m = ModeloPico().ajustar(set_ent)
    ruta = tmp_path / "modelo.txt"
    m.guardar(ruta)
    payload = json.loads(ruta.read_text())
    payload.pop("calibracion")
    ruta.write_text(json.dumps(payload))
    m2 = ModeloPico.cargar(ruta)
    assert m2.q_hat == 0.0


def test_entrenar_calibrado_calcula_q_hat():
    set_ent = _set_sintetico(n_dias=120)
    m = model.entrenar_calibrado(set_ent, dias_calibracion=30)
    assert isinstance(m.q_hat, float)
    # Con pocos días no hay split posible: sin calibración.
    m_chico = model.entrenar_calibrado(set_ent.head(11 * 10), dias_calibracion=30)
    assert m_chico.q_hat == 0.0
```

(Imports necesarios arriba del archivo: `import json`, `import numpy as np`, `from src import model`.)

Añadir a `tests/test_train.py` una aserción de que el archivo guardado trae calibración
(en el test existente que entrena, tras `train.correr`):

```python
    payload = json.loads(config.ruta_modelo().read_text())
    assert "calibracion" in payload
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/test_model.py -k "q_hat or calibra" -v`
Expected: FAIL

- [ ] **Step 3: Implementar en `src/model.py`**

En `__init__`: `self.q_hat: float = 0.0`.

`predecir` pasa a:

```python
    def predecir(self, fila: dict) -> tuple:
        X = _matriz(pd.DataFrame([{c: fila.get(c) for c in FEATURE_COLS}]))
        vals = {n: float(m.predict(X)[0]) for n, m in self._modelos.items()}
        # Calibración conformal: ensancha (o encoge) el intervalo, no el p50.
        lo = vals["p10"] - self.q_hat
        hi = vals["p90"] + self.q_hat
        # Garantiza monotonía p10 <= p50 <= p90.
        p10, p50, p90 = sorted((lo, vals["p50"], hi))
        return round(p10, 1), round(p50, 1), round(p90, 1)
```

`guardar`: el payload gana la clave de calibración:

```python
        payload = {n: m.booster_.model_to_string() for n, m in self._modelos.items()}
        payload["calibracion"] = {"q_hat": self.q_hat}
```

`cargar`: sacar la calibración ANTES de iterar los boosters:

```python
        payload = json.loads(Path(ruta).read_text())
        obj = cls()
        calib = payload.pop("calibracion", None) or {}
        obj.q_hat = float(calib.get("q_hat", 0.0))
        for n, s in payload.items():
            obj._modelos[n] = _BoosterWrap(lgb.Booster(model_str=s))
        return obj
```

Nueva función al final del módulo:

```python
def entrenar_calibrado(set_ent: pd.DataFrame,
                       dias_calibracion: int = 45) -> ModeloPico:
    """Entrena con calibración conformal (CQR) del intervalo p10-p90.

    Aparta los últimos `dias_calibracion` días como calibración, entrena con el
    resto y mide cuánto hay que ensanchar el intervalo para cubrir ~80% real
    (q_hat). Después re-entrena con todos los datos (la recencia importa) y
    conserva ese q_hat: leve sobre-cobertura, preferible a un intervalo corto.
    Sin días suficientes devuelve el modelo sin calibrar (q_hat = 0).
    """
    fechas = sorted(set_ent["fecha_objetivo"].unique())
    if len(fechas) <= dias_calibracion * 2:
        return ModeloPico().ajustar(set_ent)
    corte = fechas[-dias_calibracion]
    base = ModeloPico().ajustar(set_ent[set_ent["fecha_objetivo"] < corte])
    calib = set_ent[set_ent["fecha_objetivo"] >= corte]

    scores = []
    for _, r in calib.iterrows():
        p10, _, p90 = base.predecir(r.to_dict())
        y = float(r["target"])
        scores.append(max(p10 - y, y - p90))
    alpha = 0.2
    nivel = min(1.0, (1 - alpha) * (1 + 1 / len(scores)))
    q_hat = float(pd.Series(scores).quantile(nivel))

    final = ModeloPico().ajustar(set_ent)
    final.q_hat = q_hat
    return final
```

En `src/train.py`, reemplazar el entrenamiento:

```python
from src.model import entrenar_calibrado
...
    modelo = entrenar_calibrado(set_ent)
    modelo.guardar(config.ruta_modelo())
```

- [ ] **Step 4: Correr la suite completa**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/model.py src/train.py tests/test_model.py tests/test_train.py
git commit -m "feat: calibración conformal (CQR) del intervalo p10-p90"
```

---

### Task 7: Backtest rolling-origin mensual

**Files:**
- Create: `src/backtest.py`
- Test: `tests/test_backtest.py` (nuevo)

**Interfaces:**
- Consumes: `dataset.construir_set`, `model.entrenar_calibrado`, `storage.read_*` (Tareas 2, 5, 6).
- Produces: `backtest.correr(n_meses: int = 6, con_mpmg: bool = True) -> pd.DataFrame` (cols `mes, fecha, hora_decision, p10, pred, p90, real`); `backtest.resumen(res) -> pd.DataFrame` (métricas por mes + fila `TOTAL`); CLI `python -m src.backtest [n_meses] [--sin-mpmg]`. No escribe en `data/` ni `models/`.

- [ ] **Step 1: Tests que fallan**

Crear `tests/test_backtest.py`:

```python
import numpy as np
import pandas as pd

from src import backtest, storage


def _sembrar(tmp_path, monkeypatch, n_dias=120):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    rng = np.random.default_rng(3)
    horas, obs = [], []
    base = pd.Timestamp("2025-01-01")
    for d in range(n_dias):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in range(17):
            horas.append({"timestamp": f"{fecha}T{h:02d}:00",
                          "temp_c": 24 + h * (pico - 24) / 16,
                          "humedad": 80.0, "nubosidad": 30.0})
        obs.append({"fecha": fecha, "temp_max_c": round(pico, 1)})
    storage.upsert_hourly(horas)
    storage.upsert_observations(obs)


def test_backtest_evalua_meses_sin_fuga_temporal(tmp_path, monkeypatch):
    _sembrar(tmp_path, monkeypatch)
    res = backtest.correr(n_meses=2)
    # Solo evalúa los 2 últimos meses del dataset (mar-abr 2025).
    assert set(res["mes"]) == {"2025-03", "2025-04"}
    # Métricas razonables sobre datos sintéticos regulares.
    tabla = backtest.resumen(res)
    total = tabla.loc["TOTAL"]
    assert total["mae"] < 1.5
    assert 0.0 <= total["cobertura"] <= 1.0


def test_backtest_no_escribe_datos(tmp_path, monkeypatch):
    _sembrar(tmp_path, monkeypatch)
    antes = {p.name: p.stat().st_size for p in tmp_path.iterdir()}
    backtest.correr(n_meses=1)
    despues = {p.name: p.stat().st_size for p in tmp_path.iterdir()}
    assert antes == despues
```

- [ ] **Step 2: Verificar que fallan**

Run: `python -m pytest tests/test_backtest.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.backtest'`

- [ ] **Step 3: Crear `src/backtest.py`**

```python
"""Backtest rolling-origin mensual del modelo de pico.

Para cada uno de los últimos n meses con datos: entrena con todo lo anterior
al mes y predice cada (día, hora de decisión) del mes. Imprime MAE, sesgo,
acierto (<= UMBRAL_ACIERTO_C), cobertura y ancho del intervalo p10-p90.

Uso: python -m src.backtest [n_meses] [--sin-mpmg]
No escribe nada en data/ ni models/: es solo un harness de evaluación.
"""
import sys

import pandas as pd

from src import config, dataset, storage
from src.model import entrenar_calibrado

_MIN_FILAS_ENTRENAMIENTO = 100


def correr(n_meses: int = 6, con_mpmg: bool = True) -> pd.DataFrame:
    hist = storage.read_hourly()
    obs = storage.read_observations()
    fcst = storage.read_forecast()
    mpmg = storage.read_mpmg_hourly() if con_mpmg else None
    forecast_por_fecha = (dict(zip(fcst["fecha"], fcst["forecast_max"]))
                          if len(fcst) else {})
    total = dataset.construir_set(hist, obs, forecast_por_fecha,
                                  mpmg_horario=mpmg)
    if len(total) == 0:
        raise RuntimeError("Sin datos para el backtest; ¿falta backfill?")
    total = total.sort_values(["fecha_objetivo", "hora_decision"])

    meses = sorted(total["fecha_objetivo"].str.slice(0, 7).unique())[-n_meses:]
    filas = []
    for mes in meses:
        ent = total[total["fecha_objetivo"] < f"{mes}-01"]
        prueba = total[total["fecha_objetivo"].str.startswith(mes)]
        if len(ent) < _MIN_FILAS_ENTRENAMIENTO or len(prueba) == 0:
            print(f"{mes}: omitido (entrenamiento insuficiente: {len(ent)} filas)")
            continue
        modelo = entrenar_calibrado(ent)
        for _, r in prueba.iterrows():
            p10, p50, p90 = modelo.predecir(r.to_dict())
            filas.append({"mes": mes, "fecha": r["fecha_objetivo"],
                          "hora_decision": int(r["hora_decision"]),
                          "p10": p10, "pred": p50, "p90": p90,
                          "real": float(r["target"])})
    return pd.DataFrame(filas)


def _metricas(g: pd.DataFrame) -> pd.Series:
    err = g["pred"] - g["real"]
    return pd.Series({
        "n": len(g),
        "mae": err.abs().mean(),
        "sesgo": err.mean(),
        "acierto": (err.abs() <= config.UMBRAL_ACIERTO_C).mean(),
        "cobertura": ((g["real"] >= g["p10"]) & (g["real"] <= g["p90"])).mean(),
        "ancho": (g["p90"] - g["p10"]).mean(),
    })


def resumen(res: pd.DataFrame) -> pd.DataFrame:
    """Métricas por mes más la fila TOTAL agregada."""
    por_mes = res.groupby("mes").apply(_metricas, include_groups=False)
    por_mes.loc["TOTAL"] = _metricas(res)
    return por_mes.round(3)


def main(argv: list[str]) -> None:
    con_mpmg = "--sin-mpmg" not in argv
    pos = [a for a in argv if not a.startswith("--")]
    n_meses = int(pos[0]) if pos else 6
    res = correr(n_meses=n_meses, con_mpmg=con_mpmg)
    if len(res) == 0:
        print("Backtest sin resultados.")
        return
    etiqueta = "con features MPMG" if con_mpmg else "SIN features MPMG"
    print(f"\n=== Backtest {etiqueta} — por mes ===")
    print(resumen(res).to_string())
    print("\n=== Por hora de decisión (todos los meses) ===")
    por_hora = res.groupby("hora_decision").apply(_metricas,
                                                  include_groups=False)
    print(por_hora.round(3).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Verificar que pasa**

Run: `python -m pytest tests/test_backtest.py -v`
Expected: PASS (tarda ~1-2 min: entrena varios modelos).

- [ ] **Step 5: Commit**

```bash
git add src/backtest.py tests/test_backtest.py
git commit -m "feat: backtest rolling-origin mensual con métricas de cobertura"
```

---

### Task 8: Verificación end-to-end, despliegue y medición

**Files:**
- Modify: `README.md` (sección de arquitectura/datos: mencionar `mpmg_hourly.csv`, el backtest y la calibración)

**Interfaces:**
- Consumes: todo lo anterior; workflows existentes `backfill.yml`, `train.yml`, `hourly.yml` (sin cambios: `src.backfill` y `src.train` ya incluyen lo nuevo).

- [ ] **Step 1: Suite completa local**

Run: `python -m pytest -q`
Expected: PASS completo.

- [ ] **Step 2: Actualizar README**

Documentar en las secciones correspondientes: `data/mpmg_hourly.csv` (horario real de
la estación, fuente de `temp_actual_mpmg`/`max_hasta_ahora_mpmg`), la regla del piso,
la calibración conformal (clave `calibracion.q_hat` del modelo) y el CLI
`python -m src.backtest [n_meses] [--sin-mpmg]`.

- [ ] **Step 3: Commit y push**

```bash
git add README.md
git commit -m "docs: mpmg_hourly, backtest y calibración en el README"
git push
```

- [ ] **Step 4: Backfill del horario MPMG en Actions**

```bash
gh workflow run backfill.yml -f desde=2020-01-01
gh run watch $(gh run list --workflow=backfill.yml -L1 --json databaseId -q '.[0].databaseId')
```

Expected: verde; el commit `data: backfill…` añade `data/mpmg_hourly.csv` con datos
desde 2020 (meses sin cobertura pueden faltar, está previsto).

- [ ] **Step 5: Backtest comparativo (con datos reales, tras `git pull`)**

```bash
git pull
python -m src.backtest 6 --sin-mpmg   # baseline (equivale al modelo v1)
python -m src.backtest 6              # con features MPMG
```

Expected: MAE menor con MPMG, sobre todo a las 12–16h; cobertura p10–p90 en 70–90%.
Registrar ambas tablas en el reporte final al usuario. Si NO mejora, detenerse y
reevaluar antes de desplegar el modelo v2 (el piso de la Tarea 1 se despliega igual).

- [ ] **Step 6: Reentrenar y verificar producción**

```bash
gh workflow run train.yml
gh run watch $(gh run list --workflow=train.yml -L1 --json databaseId -q '.[0].databaseId')
gh workflow run hourly.yml
gh run watch $(gh run list --workflow=hourly.yml -L1 --json databaseId -q '.[0].databaseId')
```

Expected: ambos verdes; `data/predictions.csv` gana una fila con
`modelo_version = gbm-q-v2` y `pico_pred >= max` observado en MPMG a esa hora.

- [ ] **Step 7: Commit final si hubo ajustes**

```bash
git add -A && git commit -m "chore: ajustes post-despliegue" || echo "sin cambios"
git push
```
