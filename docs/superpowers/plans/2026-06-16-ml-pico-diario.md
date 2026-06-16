# ML del Pico Diario — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la climatología heurística por un modelo de Gradient Boosting que predice el pico (máxima) de temperatura de HOY en MPMG (Albrook, Panamá), refinándolo cada hora con datos intradía y entregando un punto (p50) + banda [p10, p90].

**Architecture:** Open-Meteo provee el histórico horario (entrenamiento), el intradía de hoy (features en vivo) y el forecast del día (feature). Wunderground MPMG provee el pico real (target/verdad). Un set de entrenamiento día×hora-de-decisión alimenta tres modelos LightGBM de cuantiles. Dos workflows separan el entrenamiento nocturno pesado de la inferencia horaria ligera.

**Tech Stack:** Python 3.12, pandas, LightGBM, requests, BeautifulSoup/Playwright (scraper Wunderground existente), pytest, GitHub Actions, GitHub Pages.

---

## Convenciones para el ejecutor

- **Trabajo remoto vía GitHub MCP** en la rama `ml-pico-diario`. No hay clon local. Cada "commit" se hace con `create_or_update_file` / `push_files` apuntando a esa rama. Donde el plan muestra `git commit`, equivale a un commit MCP con ese mensaje.
- **TDD:** escribe el test, velo fallar, implementa el mínimo, velo pasar, commitea.
- **Estación / ubicación:** MPMG, lat `8.973`, lon `-79.556`, TZ `America/Panama` (UTC-5 fijo).
- **Horas de decisión:** enteros locales `6..16` inclusive (11 horas).
- **Unidades:** todo en °C.
- Para correr tests en CI local del ejecutor: `python -m pytest -v`.

---

## Mapa de archivos

**Crear:**
- `src/sources/__init__.py` — paquete de fuentes.
- `src/sources/openmeteo.py` — archivo histórico, intradía, forecast (Open-Meteo).
- `src/sources/wunderground.py` — scraper de Wunderground (movido desde `src/scraper.py`).
- `src/features.py` — construcción de una fila de features hasta la hora H.
- `src/dataset.py` — ensamblado de la tabla de entrenamiento (día×hora).
- `src/train.py` — orquestación del reentrenamiento + guardado del modelo.
- `src/predict.py` — corrida horaria (carga modelo, predice, registra, evalúa, exporta).
- `tests/test_openmeteo.py`, `tests/test_features.py`, `tests/test_dataset.py`,
  `tests/test_model.py`, `tests/test_evaluate.py`, `tests/test_storage.py`,
  `tests/test_predict.py`.
- `.github/workflows/train.yml`, `.github/workflows/hourly.yml`.

**Modificar:**
- `src/config.py` — coordenadas, horas de decisión, rutas nuevas, versión del modelo.
- `src/model.py` — reemplazar `Climatologia/Predictor` por `ModeloPico` (cuantiles LightGBM).
- `src/storage.py` — nuevos esquemas de `predictions.csv`, `evaluation.csv`, `hourly_history.csv`.
- `src/evaluate.py` — evaluar pico predicho vs real por hora de decisión.
- `src/export.py` — payload del dashboard nuevo.
- `src/backfill.py` — cargar histórico de ambas fuentes.
- `src/scraper.py` — eliminar (movido a `src/sources/wunderground.py`).
- `src/pipeline.py` — eliminar (sustituido por `train.py` + `predict.py`).
- `.github/workflows/daily.yml` — eliminar (sustituido por los dos nuevos).
- `requirements.txt` — añadir `lightgbm`.
- `docs/index.html` / `docs/` — dashboard nuevo (Task 14).
- `README.md` — documentación nueva (Task 15).

---

## Task 1: Dependencias y config base

**Files:**
- Modify: `requirements.txt`
- Modify: `src/config.py`
- Test: `tests/test_config.py` (crear)

- [ ] **Step 1: Añadir LightGBM a requirements**

`requirements.txt` (reemplazar contenido):
```
pandas==2.2.2
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2
playwright==1.44.0
lightgbm==4.5.0
pytest==8.2.2
```

- [ ] **Step 2: Escribir el test de config**

`tests/test_config.py`:
```python
from datetime import date
from src import config


def test_coordenadas_y_horas_de_decision():
    assert abs(config.LAT - 8.973) < 0.01
    assert abs(config.LON - (-79.556)) < 0.01
    assert config.HORAS_DECISION == list(range(6, 17))
    assert config.TZ == "America/Panama"
    assert config.FECHA_INICIO == date(2020, 1, 1)


def test_rutas_de_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    assert config.ruta_observaciones().name == "observations.csv"
    assert config.ruta_predicciones().name == "predictions.csv"
    assert config.ruta_evaluacion().name == "evaluation.csv"
    assert config.ruta_historico_horario().name == "hourly_history.csv"
    assert config.ruta_modelo().name == "peak_model.txt"
```

- [ ] **Step 3: Run test (debe fallar)**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (`AttributeError: module 'src.config' has no attribute 'LAT'`)

- [ ] **Step 4: Implementar config**

`src/config.py` (reemplazar contenido):
```python
import os
from datetime import date
from pathlib import Path

# Estación de referencia (la "verdad" del pico) y ubicación para Open-Meteo.
ESTACION = "MPMG:9:PA"
LAT = 8.973
LON = -79.556
TZ = "America/Panama"

HORAS_DECISION = list(range(6, 17))  # 6am..4pm local
UMBRAL_ACIERTO_C = 1.5
FECHA_INICIO = date(2020, 1, 1)
MODELO_VERSION = "gbm-q-v1"

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"


def data_dir() -> Path:
    return Path(os.environ.get("PTF_DATA_DIR", _DEFAULT_DATA_DIR))


def model_dir() -> Path:
    return Path(os.environ.get("PTF_MODEL_DIR", _DEFAULT_MODEL_DIR))


def ruta_observaciones() -> Path:
    return data_dir() / "observations.csv"


def ruta_predicciones() -> Path:
    return data_dir() / "predictions.csv"


def ruta_evaluacion() -> Path:
    return data_dir() / "evaluation.csv"


def ruta_historico_horario() -> Path:
    return data_dir() / "hourly_history.csv"


def ruta_modelo() -> Path:
    return model_dir() / "peak_model.txt"
```

- [ ] **Step 5: Run test (debe pasar)**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/config.py tests/test_config.py
git commit -m "feat: config base para ML del pico (coords, horas, rutas, lightgbm)"
```

---

## Task 2: Fuente Open-Meteo — parseo del archivo histórico

**Files:**
- Create: `src/sources/__init__.py`
- Create: `src/sources/openmeteo.py`
- Test: `tests/test_openmeteo.py`

- [ ] **Step 1: Crear el paquete**

`src/sources/__init__.py`:
```python
```
(archivo vacío)

- [ ] **Step 2: Escribir el test del parser de archivo**

`tests/test_openmeteo.py`:
```python
from src.sources import openmeteo


def test_parse_archivo_horario_a_filas():
    payload = {
        "hourly": {
            "time": ["2020-01-01T00:00", "2020-01-01T01:00", "2020-01-01T02:00"],
            "temperature_2m": [24.0, 23.5, 23.0],
            "relative_humidity_2m": [80, 82, 85],
            "cloud_cover": [10, 20, 30],
        }
    }
    filas = openmeteo.parse_horario(payload)
    assert filas[0] == {
        "timestamp": "2020-01-01T00:00",
        "temp_c": 24.0,
        "humedad": 80.0,
        "nubosidad": 10.0,
    }
    assert len(filas) == 3


def test_parse_horario_omite_nulos():
    payload = {
        "hourly": {
            "time": ["2020-01-01T00:00", "2020-01-01T01:00"],
            "temperature_2m": [None, 23.5],
            "relative_humidity_2m": [80, 82],
            "cloud_cover": [10, 20],
        }
    }
    filas = openmeteo.parse_horario(payload)
    assert len(filas) == 1
    assert filas[0]["timestamp"] == "2020-01-01T01:00"
```

- [ ] **Step 3: Run test (debe fallar)**

Run: `python -m pytest tests/test_openmeteo.py -v`
Expected: FAIL (`ModuleNotFoundError` / `AttributeError: parse_horario`)

- [ ] **Step 4: Implementar el parser**

`src/sources/openmeteo.py`:
```python
import requests

from src import config

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 60
_HOURLY_VARS = "temperature_2m,relative_humidity_2m,cloud_cover"


def parse_horario(payload: dict) -> list[dict]:
    """Convierte la respuesta `hourly` de Open-Meteo en filas; omite temp nula."""
    h = payload.get("hourly", {})
    tiempos = h.get("time", [])
    temps = h.get("temperature_2m", [])
    hums = h.get("relative_humidity_2m", [])
    nubes = h.get("cloud_cover", [])
    filas = []
    for i, ts in enumerate(tiempos):
        if temps[i] is None:
            continue
        filas.append({
            "timestamp": ts,
            "temp_c": float(temps[i]),
            "humedad": float(hums[i]) if hums[i] is not None else None,
            "nubosidad": float(nubes[i]) if nubes[i] is not None else None,
        })
    return filas
```

- [ ] **Step 5: Run test (debe pasar)**

Run: `python -m pytest tests/test_openmeteo.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sources/__init__.py src/sources/openmeteo.py tests/test_openmeteo.py
git commit -m "feat: parser de archivo horario de Open-Meteo"
```

---

## Task 3: Open-Meteo — fetch de archivo, intradía y forecast

**Files:**
- Modify: `src/sources/openmeteo.py`
- Test: `tests/test_openmeteo.py`

- [ ] **Step 1: Escribir tests con requests mockeado**

Añadir a `tests/test_openmeteo.py`:
```python
from datetime import date
from unittest.mock import patch


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_fetch_archivo_arma_params_y_parsea():
    data = {"hourly": {"time": ["2020-01-01T00:00"], "temperature_2m": [24.0],
                       "relative_humidity_2m": [80], "cloud_cover": [10]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)) as g:
        filas = openmeteo.fetch_archivo(date(2020, 1, 1), date(2020, 1, 2))
    assert filas[0]["temp_c"] == 24.0
    _, kwargs = g.call_args
    assert kwargs["params"]["start_date"] == "2020-01-01"
    assert kwargs["params"]["end_date"] == "2020-01-02"
    assert kwargs["params"]["timezone"] == "America/Panama"


def test_fetch_forecast_maxima_de_hoy():
    data = {"daily": {"time": ["2026-06-16"], "temperature_2m_max": [33.4]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)):
        val = openmeteo.fetch_forecast_max(date(2026, 6, 16))
    assert val == 33.4


def test_fetch_intradia_usa_past_days():
    data = {"hourly": {"time": ["2026-06-16T00:00"], "temperature_2m": [26.0],
                       "relative_humidity_2m": [88], "cloud_cover": [40]}}
    with patch("src.sources.openmeteo.requests.get", return_value=_Resp(data)) as g:
        filas = openmeteo.fetch_intradia(date(2026, 6, 16))
    assert filas[0]["temp_c"] == 26.0
    _, kwargs = g.call_args
    assert kwargs["params"]["past_days"] >= 1
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_openmeteo.py -v`
Expected: FAIL (`AttributeError: fetch_archivo`)

- [ ] **Step 3: Implementar los fetch**

Añadir a `src/sources/openmeteo.py`:
```python
def fetch_archivo(desde: "date", hasta: "date") -> list[dict]:
    """Histórico horario [desde, hasta] desde el archivo ERA5 de Open-Meteo."""
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "start_date": desde.isoformat(),
        "end_date": hasta.isoformat(),
        "hourly": _HOURLY_VARS,
        "timezone": config.TZ,
    }
    resp = requests.get(ARCHIVE_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return parse_horario(resp.json())


def fetch_intradia(hoy: "date") -> list[dict]:
    """Horario de hoy (y ayer) desde la API de forecast con past_days."""
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "hourly": _HOURLY_VARS,
        "timezone": config.TZ,
        "past_days": 1,
        "forecast_days": 1,
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    filas = parse_horario(resp.json())
    hoy_iso = hoy.isoformat()
    return [f for f in filas if f["timestamp"].startswith(hoy_iso)]


def fetch_forecast_max(hoy: "date") -> float | None:
    """Máxima diaria pronosticada por Open-Meteo para hoy (feature)."""
    params = {
        "latitude": config.LAT,
        "longitude": config.LON,
        "daily": "temperature_2m_max",
        "timezone": config.TZ,
        "start_date": hoy.isoformat(),
        "end_date": hoy.isoformat(),
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    vals = daily.get("temperature_2m_max", [])
    return float(vals[0]) if vals and vals[0] is not None else None
```

Añadir `from datetime import date` al tope del módulo.

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_openmeteo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sources/openmeteo.py tests/test_openmeteo.py
git commit -m "feat: fetch de archivo, intradia y forecast de Open-Meteo"
```

---

## Task 4: Mover el scraper de Wunderground a `sources/`

**Files:**
- Create: `src/sources/wunderground.py` (contenido movido desde `src/scraper.py`)
- Delete: `src/scraper.py`
- Test: `tests/test_wunderground.py` (crear)

- [ ] **Step 1: Crear el módulo movido**

Crear `src/sources/wunderground.py` con el contenido **idéntico** del actual
`src/scraper.py` (parser `parse_historical_json`, `fetch_via_api`, `f_a_c`,
`parse_history_html`, `fetch_via_browser`, `obtener_observaciones`).
Mantener `from src import config`.

- [ ] **Step 2: Escribir un test mínimo de regresión**

`tests/test_wunderground.py`:
```python
from src.sources import wunderground


def test_parse_historical_json_agrupa_por_dia_y_toma_maximo():
    payload = {"observations": [
        {"valid_time_gmt": 1577880000, "temp": 28.0},
        {"valid_time_gmt": 1577883600, "temp": 31.0},
    ]}
    filas = wunderground.parse_historical_json(payload)
    assert len(filas) == 1
    assert filas[0]["temp_max_c"] == 31.0


def test_f_a_c_convierte_fahrenheit():
    assert wunderground.f_a_c(89.6) == 32.0
```

- [ ] **Step 3: Run test (debe pasar tras crear el módulo)**

Run: `python -m pytest tests/test_wunderground.py -v`
Expected: PASS

- [ ] **Step 4: Eliminar el scraper viejo**

Borrar `src/scraper.py`. (Vía MCP: `delete_file`.)

- [ ] **Step 5: Commit**

```bash
git add src/sources/wunderground.py tests/test_wunderground.py
git rm src/scraper.py
git commit -m "refactor: mover scraper de Wunderground a src/sources/wunderground.py"
```

---

## Task 5: Almacenamiento — esquemas nuevos

**Files:**
- Modify: `src/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Escribir tests de storage**

`tests/test_storage.py`:
```python
import pandas as pd
from src import storage


def test_observations_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_observations([{"fecha": "2020-01-01", "temp_max_c": 31.0}])
    storage.upsert_observations([{"fecha": "2020-01-01", "temp_max_c": 32.0},
                                 {"fecha": "2020-01-02", "temp_max_c": 30.0}])
    df = storage.read_observations()
    assert len(df) == 2
    assert df.set_index("fecha").loc["2020-01-01", "temp_max_c"] == 32.0


def test_hourly_history_roundtrip_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    storage.upsert_hourly([{"timestamp": "2020-01-01T00:00", "temp_c": 24.0,
                            "humedad": 80.0, "nubosidad": 10.0}])
    storage.upsert_hourly([{"timestamp": "2020-01-01T00:00", "temp_c": 25.0,
                            "humedad": 81.0, "nubosidad": 11.0}])
    df = storage.read_hourly()
    assert len(df) == 1
    assert df.iloc[0]["temp_c"] == 25.0


def test_predictions_append(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    fila = {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
            "hora_decision": 6, "pico_pred": 33.0, "p10": 31.5, "p90": 34.5,
            "modelo_version": "gbm-q-v1"}
    storage.append_prediction(fila)
    storage.append_prediction({**fila, "hora_decision": 7})
    df = storage.read_predictions()
    assert len(df) == 2
    assert set(df.columns) == set(fila.keys())


def test_evaluation_write_read(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    ev = pd.DataFrame([{"fecha_objetivo": "2026-06-15", "hora_decision": 12,
                        "pico_pred": 33.0, "pico_real": 32.4, "error_c": 0.6}])
    storage.write_evaluation(ev)
    df = storage.read_evaluation()
    assert df.iloc[0]["error_c"] == 0.6
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL (`AttributeError: upsert_hourly` / columnas distintas)

- [ ] **Step 3: Implementar storage**

`src/storage.py` (reemplazar contenido):
```python
import pandas as pd

from src import config

_PRED_COLS = ["run_timestamp", "fecha_objetivo", "hora_decision", "pico_pred",
              "p10", "p90", "modelo_version"]
_EVAL_COLS = ["fecha_objetivo", "hora_decision", "pico_pred", "pico_real", "error_c"]
_HOURLY_COLS = ["timestamp", "temp_c", "humedad", "nubosidad"]
_OBS_COLS = ["fecha", "temp_max_c"]


def _read_csv(ruta, cols) -> pd.DataFrame:
    if ruta.exists():
        return pd.read_csv(ruta)
    return pd.DataFrame(columns=cols)


def read_observations() -> pd.DataFrame:
    return _read_csv(config.ruta_observaciones(), _OBS_COLS)


def upsert_observations(filas: list[dict]) -> None:
    ruta = config.ruta_observaciones()
    df = pd.concat([read_observations(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates("fecha", keep="last").sort_values("fecha")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_hourly() -> pd.DataFrame:
    return _read_csv(config.ruta_historico_horario(), _HOURLY_COLS)


def upsert_hourly(filas: list[dict]) -> None:
    ruta = config.ruta_historico_horario()
    df = pd.concat([read_hourly(), pd.DataFrame(filas)], ignore_index=True)
    df = df.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_predictions() -> pd.DataFrame:
    return _read_csv(config.ruta_predicciones(), _PRED_COLS)


def append_prediction(fila: dict) -> None:
    ruta = config.ruta_predicciones()
    df = pd.concat([read_predictions(), pd.DataFrame([fila])], ignore_index=True)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_evaluation() -> pd.DataFrame:
    return _read_csv(config.ruta_evaluacion(), _EVAL_COLS)


def write_evaluation(df: pd.DataFrame) -> None:
    ruta = config.ruta_evaluacion()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/storage.py tests/test_storage.py
git commit -m "feat: esquemas de almacenamiento nuevos (horario, predicciones, evaluacion)"
```

---

## Task 6: Features — fila a partir de intradía hasta la hora H

**Files:**
- Create: `src/features.py`
- Test: `tests/test_features.py`

- [ ] **Step 1: Escribir el test de features**

`tests/test_features.py`:
```python
import pandas as pd
from src import features


def _intradia():
    # Horas 0..10 de un día, temperatura subiendo.
    return pd.DataFrame({
        "timestamp": [f"2026-06-16T{h:02d}:00" for h in range(11)],
        "temp_c": [24, 24, 23, 23, 24, 26, 28, 29, 30, 31, 31.5],
        "humedad": [88]*11,
        "nubosidad": [40]*11,
    })


def test_construir_fila_hasta_hora_h():
    fila = features.construir_fila(_intradia(), fecha="2026-06-16",
                                   hora_h=9, forecast_max=33.0)
    assert fila["hora_decision"] == 9
    assert fila["max_hasta_ahora"] == 31.0        # max de horas 0..9
    assert fila["temp_actual"] == 31.0            # hora 9
    assert fila["forecast_max"] == 33.0
    assert "doy_sin" in fila and "doy_cos" in fila
    assert fila["temp_lag1"] == 30.0              # hora 8
    assert round(fila["tasa_subida"], 2) == 1.0   # (31 - 30) por hora


def test_construir_fila_ignora_horas_posteriores_a_h():
    fila = features.construir_fila(_intradia(), fecha="2026-06-16",
                                   hora_h=6, forecast_max=None)
    assert fila["max_hasta_ahora"] == 28.0        # no ve las horas 7..10
    assert fila["forecast_max"] is None


def test_construir_fila_forecast_nullable():
    fila = features.construir_fila(_intradia(), fecha="2026-06-16",
                                   hora_h=10, forecast_max=None)
    assert fila["forecast_max"] is None
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_features.py -v`
Expected: FAIL (`ModuleNotFoundError: src.features`)

- [ ] **Step 3: Implementar features**

`src/features.py`:
```python
import math

import pandas as pd

# Orden canónico de columnas de features (lo consume dataset/model/predict).
FEATURE_COLS = [
    "hora_decision", "doy_sin", "doy_cos", "mes",
    "max_hasta_ahora", "temp_actual", "temp_lag1", "temp_lag2", "temp_lag3",
    "tasa_subida", "humedad_actual", "nubosidad_actual", "forecast_max",
]


def _hora(ts: str) -> int:
    return int(ts[11:13])


def construir_fila(intradia: pd.DataFrame, fecha: str, hora_h: int,
                   forecast_max: float | None) -> dict:
    """Construye una fila de features usando solo horas <= hora_h del día `fecha`."""
    df = intradia.copy()
    df = df[df["timestamp"].str.startswith(fecha)]
    df = df.assign(_h=df["timestamp"].map(_hora)).sort_values("_h")
    hasta = df[df["_h"] <= hora_h]

    fecha_ts = pd.Timestamp(fecha)
    doy = fecha_ts.dayofyear

    def _temp_en(h: int):
        sel = hasta[hasta["_h"] == h]["temp_c"]
        return float(sel.iloc[0]) if len(sel) else None

    temp_actual = _temp_en(hora_h)
    temp_lag1 = _temp_en(hora_h - 1)
    temp_lag2 = _temp_en(hora_h - 2)
    temp_lag3 = _temp_en(hora_h - 3)
    tasa = (temp_actual - temp_lag1) if (temp_actual is not None
                                         and temp_lag1 is not None) else None

    def _ultimo(col: str):
        sel = hasta[col].dropna()
        return float(sel.iloc[-1]) if len(sel) else None

    return {
        "fecha_objetivo": fecha,
        "hora_decision": hora_h,
        "doy_sin": math.sin(2 * math.pi * doy / 365.25),
        "doy_cos": math.cos(2 * math.pi * doy / 365.25),
        "mes": fecha_ts.month,
        "max_hasta_ahora": float(hasta["temp_c"].max()) if len(hasta) else None,
        "temp_actual": temp_actual,
        "temp_lag1": temp_lag1,
        "temp_lag2": temp_lag2,
        "temp_lag3": temp_lag3,
        "tasa_subida": tasa,
        "humedad_actual": _ultimo("humedad"),
        "nubosidad_actual": _ultimo("nubosidad"),
        "forecast_max": forecast_max,
    }
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_features.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/features.py tests/test_features.py
git commit -m "feat: construccion de fila de features intradia hasta la hora H"
```

---

## Task 7: Dataset — tabla de entrenamiento día×hora

**Files:**
- Create: `src/dataset.py`
- Test: `tests/test_dataset.py`

- [ ] **Step 1: Escribir el test de dataset**

`tests/test_dataset.py`:
```python
import pandas as pd
from src import dataset, config


def _hist_horario():
    filas = []
    for dia in ("2026-06-14", "2026-06-15"):
        for h in range(17):
            filas.append({"timestamp": f"{dia}T{h:02d}:00",
                          "temp_c": 24 + h * 0.5,
                          "humedad": 80.0, "nubosidad": 30.0})
    return pd.DataFrame(filas)


def _observaciones():
    return pd.DataFrame([
        {"fecha": "2026-06-14", "temp_max_c": 32.0},
        {"fecha": "2026-06-15", "temp_max_c": 33.0},
    ])


def test_construir_set_genera_una_fila_por_dia_y_hora():
    df = dataset.construir_set(_hist_horario(), _observaciones())
    # 2 días * len(HORAS_DECISION) filas
    assert len(df) == 2 * len(config.HORAS_DECISION)
    assert "target" in df.columns
    # El target es el pico real del día correspondiente.
    fila_14 = df[df["fecha_objetivo"] == "2026-06-14"].iloc[0]
    assert fila_14["target"] == 32.0


def test_construir_set_omite_dias_sin_observacion():
    obs = _observaciones().iloc[:1]  # solo 2026-06-14
    df = dataset.construir_set(_hist_horario(), obs)
    assert set(df["fecha_objetivo"].unique()) == {"2026-06-14"}
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_dataset.py -v`
Expected: FAIL (`ModuleNotFoundError: src.dataset`)

- [ ] **Step 3: Implementar dataset**

`src/dataset.py`:
```python
import pandas as pd

from src import config, features


def construir_set(hist_horario: pd.DataFrame, observaciones: pd.DataFrame) -> pd.DataFrame:
    """Ensambla la tabla de entrenamiento: una fila por (día observado × hora de decisión).

    El forecast histórico no está disponible en backfill, así que `forecast_max` = None
    (LightGBM lo trata como faltante). El target es el pico real (Wunderground).
    """
    obs = observaciones.dropna(subset=["temp_max_c"]).copy()
    target_por_fecha = dict(zip(obs["fecha"], obs["temp_max_c"]))

    df = hist_horario.copy()
    df["_fecha"] = df["timestamp"].str.slice(0, 10)

    filas = []
    for fecha, intradia in df.groupby("_fecha"):
        if fecha not in target_por_fecha:
            continue
        for h in config.HORAS_DECISION:
            fila = features.construir_fila(intradia, fecha=fecha, hora_h=h,
                                           forecast_max=None)
            if fila["max_hasta_ahora"] is None:
                continue
            fila["target"] = float(target_por_fecha[fecha])
            filas.append(fila)
    return pd.DataFrame(filas)
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_dataset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dataset.py tests/test_dataset.py
git commit -m "feat: ensamblado de la tabla de entrenamiento dia x hora"
```

---

## Task 8: Modelo — LightGBM por cuantiles tras interfaz `ajustar/predecir`

**Files:**
- Modify: `src/model.py` (reemplazar `Climatologia`/`Predictor`)
- Test: `tests/test_model.py`

- [ ] **Step 1: Escribir el test del modelo**

`tests/test_model.py`:
```python
import numpy as np
import pandas as pd
from src import dataset, config
from src.model import ModeloPico


def _set_entrenamiento(n_dias=60):
    rng = np.random.default_rng(0)
    filas = []
    base = pd.Timestamp("2025-01-01")
    for d in range(n_dias):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in config.HORAS_DECISION:
            filas.append({
                "fecha_objetivo": fecha, "hora_decision": h,
                "doy_sin": 0.1, "doy_cos": 0.1, "mes": 6,
                "max_hasta_ahora": 24 + h * 0.4,
                "temp_actual": 24 + h * 0.4, "temp_lag1": 24 + (h-1) * 0.4,
                "temp_lag2": 23, "temp_lag3": 23, "tasa_subida": 0.4,
                "humedad_actual": 80, "nubosidad_actual": 30, "forecast_max": pico,
                "target": pico,
            })
    return pd.DataFrame(filas)


def test_ajustar_y_predecir_cuantiles_ordenados():
    df = _set_entrenamiento()
    modelo = ModeloPico().ajustar(df)
    fila = df.iloc[-1].to_dict()
    p10, p50, p90 = modelo.predecir(fila)
    assert p10 <= p50 <= p90
    assert 25 < p50 < 40


def test_persistencia_roundtrip(tmp_path):
    df = _set_entrenamiento()
    modelo = ModeloPico().ajustar(df)
    ruta = tmp_path / "m.txt"
    modelo.guardar(ruta)
    cargado = ModeloPico.cargar(ruta)
    fila = df.iloc[-1].to_dict()
    assert cargado.predecir(fila)[1] == modelo.predecir(fila)[1]
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_model.py -v`
Expected: FAIL (`ImportError: cannot import name 'ModeloPico'`)

- [ ] **Step 3: Implementar el modelo**

`src/model.py` (reemplazar contenido):
```python
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.features import FEATURE_COLS

_CUANTILES = {"p10": 0.10, "p50": 0.50, "p90": 0.90}
_PARAMS = {
    "objective": "quantile",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "verbose": -1,
}


class ModeloPico:
    """Tres regresores LightGBM de cuantiles (p10/p50/p90) tras ajustar/predecir."""

    def __init__(self):
        self._modelos: dict[str, lgb.LGBMRegressor] = {}

    def ajustar(self, set_entrenamiento: pd.DataFrame) -> "ModeloPico":
        X = set_entrenamiento[FEATURE_COLS]
        y = set_entrenamiento["target"]
        for nombre, alpha in _CUANTILES.items():
            m = lgb.LGBMRegressor(alpha=alpha, **_PARAMS)
            m.fit(X, y)
            self._modelos[nombre] = m
        return self

    def predecir(self, fila: dict) -> tuple[float, float, float]:
        X = pd.DataFrame([{c: fila.get(c) for c in FEATURE_COLS}])[FEATURE_COLS]
        vals = {n: float(m.predict(X)[0]) for n, m in self._modelos.items()}
        # Garantiza monotonía p10 <= p50 <= p90.
        p10, p50, p90 = sorted((vals["p10"], vals["p50"], vals["p90"]))
        return round(p10, 1), round(p50, 1), round(p90, 1)

    def guardar(self, ruta: "Path") -> None:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        payload = {n: m.booster_.model_to_string() for n, m in self._modelos.items()}
        ruta.write_text(json.dumps(payload))

    @classmethod
    def cargar(cls, ruta: "Path") -> "ModeloPico":
        payload = json.loads(Path(ruta).read_text())
        obj = cls()
        for n, s in payload.items():
            booster = lgb.Booster(model_str=s)
            reg = lgb.LGBMRegressor()
            reg._Booster = booster
            reg.fitted_ = True
            obj._modelos[n] = _BoosterWrap(booster)
        return obj


class _BoosterWrap:
    """Envuelve un Booster cargado para exponer .predict como el regresor."""

    def __init__(self, booster: lgb.Booster):
        self._b = booster

    def predict(self, X):
        return self._b.predict(X)
```

> Nota de implementación: al cargar usamos `_BoosterWrap` para predecir desde el
> Booster serializado sin re-entrenar. Si el ejecutor prefiere, puede serializar
> con `joblib`/`pickle` de los `LGBMRegressor` completos; mantener la misma
> interfaz `guardar/cargar` y los tests pasan igual.

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/model.py tests/test_model.py
git commit -m "feat: ModeloPico LightGBM por cuantiles con persistencia"
```

---

## Task 9: Evaluación — pico predicho vs real por hora

**Files:**
- Modify: `src/evaluate.py`
- Test: `tests/test_evaluate.py`

- [ ] **Step 1: Escribir el test de evaluación**

`tests/test_evaluate.py`:
```python
import pandas as pd
from src import evaluate


def test_evaluar_calcula_error_por_hora():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-15T11:00:00", "fecha_objetivo": "2026-06-15",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31, "p90": 35,
         "modelo_version": "gbm-q-v1"},
        {"run_timestamp": "2026-06-15T17:00:00", "fecha_objetivo": "2026-06-15",
         "hora_decision": 12, "pico_pred": 32.5, "p10": 32, "p90": 33,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-15", "temp_max_c": 32.4}])
    ev = evaluate.evaluar(predicciones, observaciones)
    assert len(ev) == 2
    fila12 = ev[ev["hora_decision"] == 12].iloc[0]
    assert fila12["pico_real"] == 32.4
    assert round(fila12["error_c"], 1) == 0.1


def test_evaluar_omite_dias_sin_observacion():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31, "p90": 35,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame(columns=["fecha", "temp_max_c"])
    ev = evaluate.evaluar(predicciones, observaciones)
    assert len(ev) == 0
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_evaluate.py -v`
Expected: FAIL (la firma actual no calcula por hora)

- [ ] **Step 3: Implementar evaluate**

`src/evaluate.py` (reemplazar contenido):
```python
import pandas as pd


def evaluar(predicciones: pd.DataFrame, observaciones: pd.DataFrame) -> pd.DataFrame:
    """Compara cada predicción horaria contra el pico real del día.

    Devuelve filas: fecha_objetivo, hora_decision, pico_pred, pico_real, error_c.
    Solo incluye días con observación (pico real) ya disponible.
    """
    if len(predicciones) == 0 or len(observaciones) == 0:
        return pd.DataFrame(columns=["fecha_objetivo", "hora_decision",
                                     "pico_pred", "pico_real", "error_c"])
    real = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for _, p in predicciones.iterrows():
        f = p["fecha_objetivo"]
        if f not in real:
            continue
        pr = float(real[f])
        filas.append({
            "fecha_objetivo": f,
            "hora_decision": int(p["hora_decision"]),
            "pico_pred": float(p["pico_pred"]),
            "pico_real": pr,
            "error_c": round(float(p["pico_pred"]) - pr, 2),
        })
    return pd.DataFrame(filas)
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_evaluate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/evaluate.py tests/test_evaluate.py
git commit -m "feat: evaluacion del pico predicho vs real por hora de decision"
```

---

## Task 10: Export — payload del dashboard

**Files:**
- Modify: `src/export.py`
- Test: `tests/test_export.py` (crear)

- [ ] **Step 1: Escribir el test de export**

`tests/test_export.py`:
```python
import json
import pandas as pd
from src import export


def test_construir_payload_estructura():
    predicciones = pd.DataFrame([
        {"run_timestamp": "2026-06-16T11:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 6, "pico_pred": 33.0, "p10": 31.5, "p90": 34.5,
         "modelo_version": "gbm-q-v1"},
        {"run_timestamp": "2026-06-16T17:00:00", "fecha_objetivo": "2026-06-16",
         "hora_decision": 12, "pico_pred": 32.8, "p10": 32.2, "p90": 33.4,
         "modelo_version": "gbm-q-v1"},
    ])
    observaciones = pd.DataFrame([{"fecha": "2026-06-15", "temp_max_c": 32.4}])
    evaluacion = pd.DataFrame([{"fecha_objetivo": "2026-06-15", "hora_decision": 12,
                               "pico_pred": 32.5, "pico_real": 32.4, "error_c": 0.1}])
    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy="2026-06-16")
    assert payload["hoy"] == "2026-06-16"
    # La predicción más reciente de hoy manda el número grande.
    assert payload["pico_hoy"]["pico_pred"] == 32.8
    assert payload["pico_hoy"]["p10"] == 32.2
    assert payload["pico_hoy"]["p90"] == 33.4
    assert len(payload["convergencia_hoy"]) == 2
    assert "error_por_hora" in payload


def test_exportar_escribe_json(tmp_path):
    payload = {"hoy": "2026-06-16", "pico_hoy": None,
               "convergencia_hoy": [], "error_por_hora": []}
    ruta = tmp_path / "data.json"
    export.exportar(ruta, payload)
    assert json.loads(ruta.read_text())["hoy"] == "2026-06-16"
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_export.py -v`
Expected: FAIL (firma de `construir_payload` distinta)

- [ ] **Step 3: Implementar export**

`src/export.py` (reemplazar contenido):
```python
import json
from pathlib import Path

import pandas as pd


def construir_payload(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
                      evaluacion: pd.DataFrame, hoy: str) -> dict:
    hoy_preds = predicciones[predicciones["fecha_objetivo"] == hoy] \
        .sort_values("hora_decision")

    pico_hoy = None
    convergencia = []
    if len(hoy_preds):
        ult = hoy_preds.iloc[-1]
        pico_hoy = {"pico_pred": float(ult["pico_pred"]),
                    "p10": float(ult["p10"]), "p90": float(ult["p90"]),
                    "hora_decision": int(ult["hora_decision"])}
        convergencia = [{"hora_decision": int(r["hora_decision"]),
                         "pico_pred": float(r["pico_pred"]),
                         "p10": float(r["p10"]), "p90": float(r["p90"])}
                        for _, r in hoy_preds.iterrows()]

    error_por_hora = []
    if len(evaluacion):
        g = evaluacion.assign(abs_err=evaluacion["error_c"].abs()) \
            .groupby("hora_decision")["abs_err"].mean().reset_index()
        error_por_hora = [{"hora_decision": int(r["hora_decision"]),
                           "error_medio_abs": round(float(r["abs_err"]), 2)}
                          for _, r in g.iterrows()]

    observados = [{"fecha": r["fecha"], "temp_max_c": float(r["temp_max_c"])}
                  for _, r in observaciones.tail(30).iterrows()]

    return {
        "hoy": hoy,
        "pico_hoy": pico_hoy,
        "convergencia_hoy": convergencia,
        "error_por_hora": error_por_hora,
        "observados_recientes": observados,
    }


def exportar(ruta: "Path", payload: dict) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat: payload del dashboard (pico de hoy, convergencia, error por hora)"
```

---

## Task 11: Backfill — histórico de ambas fuentes

**Files:**
- Modify: `src/backfill.py`
- Test: `tests/test_backfill.py` (crear)

- [ ] **Step 1: Escribir el test de backfill (con fetch mockeado)**

`tests/test_backfill.py`:
```python
from datetime import date
from unittest.mock import patch
from src import backfill, storage


def test_backfill_carga_horario_y_observaciones(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    horas = [{"timestamp": "2020-01-01T10:00", "temp_c": 30.0,
              "humedad": 80.0, "nubosidad": 20.0}]
    obs = [{"fecha": "2020-01-01", "temp_max_c": 31.0}]
    with patch("src.backfill.openmeteo.fetch_archivo", return_value=horas), \
         patch("src.backfill.wunderground.obtener_observaciones", return_value=obs):
        backfill.correr(desde=date(2020, 1, 1), hasta=date(2020, 1, 1))
    assert len(storage.read_hourly()) == 1
    assert len(storage.read_observations()) == 1
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: FAIL (firma/imports distintos)

- [ ] **Step 3: Implementar backfill**

`src/backfill.py` (reemplazar contenido):
```python
import sys
from datetime import date, timedelta

from src import config, storage
from src.sources import openmeteo, wunderground


def correr(desde: date | None = None, hasta: date | None = None) -> None:
    desde = desde or config.FECHA_INICIO
    hasta = hasta or (date.today() - timedelta(days=1))

    # 1. Histórico horario (Open-Meteo) en bloques anuales para no pedir todo de una.
    bloque_ini = desde
    while bloque_ini <= hasta:
        bloque_fin = min(date(bloque_ini.year, 12, 31), hasta)
        filas = openmeteo.fetch_archivo(bloque_ini, bloque_fin)
        if filas:
            storage.upsert_hourly(filas)
        bloque_ini = date(bloque_ini.year + 1, 1, 1)

    # 2. Picos diarios reales (Wunderground MPMG).
    obs = wunderground.obtener_observaciones(desde, hasta)
    if obs:
        storage.upsert_observations(obs)


if __name__ == "__main__":
    desde = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    correr(desde=desde)
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/backfill.py tests/test_backfill.py
git commit -m "feat: backfill de historico horario (Open-Meteo) y picos (Wunderground)"
```

---

## Task 12: Entrenamiento — `train.py`

**Files:**
- Create: `src/train.py`
- Test: `tests/test_train.py` (crear)

- [ ] **Step 1: Escribir el test de train (componible)**

`tests/test_train.py`:
```python
from datetime import date
from unittest.mock import patch
import numpy as np
import pandas as pd
from src import train, config, storage
from src.model import ModeloPico


def _sembrar_datos(tmp_path):
    rng = np.random.default_rng(1)
    horas, obs = [], []
    base = pd.Timestamp("2025-01-01")
    for d in range(40):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in range(17):
            horas.append({"timestamp": f"{fecha}T{h:02d}:00",
                          "temp_c": 24 + h * (pico - 24) / 16,
                          "humedad": 80.0, "nubosidad": 30.0})
        obs.append({"fecha": fecha, "temp_max_c": round(pico, 1)})
    storage.upsert_hourly(horas)
    storage.upsert_observations(obs)


def test_train_entrena_y_guarda_modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    _sembrar_datos(tmp_path)
    # No tocar la red: el backfill incremental se omite en el test.
    with patch("src.train.backfill.correr"):
        train.correr(incremental=False)
    assert config.ruta_modelo().exists()
    modelo = ModeloPico.cargar(config.ruta_modelo())
    fila = {"hora_decision": 12, "doy_sin": 0.1, "doy_cos": 0.1, "mes": 1,
            "max_hasta_ahora": 30, "temp_actual": 30, "temp_lag1": 29,
            "temp_lag2": 28, "temp_lag3": 27, "tasa_subida": 1.0,
            "humedad_actual": 80, "nubosidad_actual": 30, "forecast_max": None}
    p10, p50, p90 = modelo.predecir(fila)
    assert p10 <= p50 <= p90
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_train.py -v`
Expected: FAIL (`ModuleNotFoundError: src.train`)

- [ ] **Step 3: Implementar train**

`src/train.py`:
```python
from src import backfill, config, dataset, storage
from src.model import ModeloPico


def correr(incremental: bool = True) -> None:
    # 1. Traer días nuevos antes de reentrenar.
    if incremental:
        backfill.correr()

    # 2. Ensamblar el set y entrenar.
    hist = storage.read_hourly()
    obs = storage.read_observations()
    set_ent = dataset.construir_set(hist, obs)
    if len(set_ent) == 0:
        raise RuntimeError("Set de entrenamiento vacío; ¿falta backfill?")

    modelo = ModeloPico().ajustar(set_ent)
    modelo.guardar(config.ruta_modelo())


if __name__ == "__main__":
    correr()
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_train.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/train.py tests/test_train.py
git commit -m "feat: orquestacion de entrenamiento nocturno (train.py)"
```

---

## Task 13: Corrida horaria — `predict.py`

**Files:**
- Create: `src/predict.py`
- Delete: `src/pipeline.py`
- Test: `tests/test_predict.py`

- [ ] **Step 1: Escribir el test de predict (red mockeada)**

`tests/test_predict.py`:
```python
from datetime import date
from unittest.mock import patch
import numpy as np
import pandas as pd
from src import predict, config, storage, train
from src.model import ModeloPico


def _sembrar_y_entrenar(tmp_path):
    rng = np.random.default_rng(2)
    horas, obs = [], []
    base = pd.Timestamp("2025-01-01")
    for d in range(40):
        fecha = (base + pd.Timedelta(days=d)).date().isoformat()
        pico = 32 + rng.normal(0, 1)
        for h in range(17):
            horas.append({"timestamp": f"{fecha}T{h:02d}:00",
                          "temp_c": 24 + h * (pico - 24) / 16,
                          "humedad": 80.0, "nubosidad": 30.0})
        obs.append({"fecha": fecha, "temp_max_c": round(pico, 1)})
    storage.upsert_hourly(horas)
    storage.upsert_observations(obs)
    with patch("src.train.backfill.correr"):
        train.correr(incremental=False)


def test_predict_registra_prediccion_de_hoy(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    _sembrar_y_entrenar(tmp_path)

    hoy = date(2026, 6, 16)
    intradia = [{"timestamp": f"2026-06-16T{h:02d}:00", "temp_c": 24 + h * 0.5,
                 "humedad": 85.0, "nubosidad": 40.0} for h in range(11)]
    with patch("src.predict.openmeteo.fetch_intradia", return_value=intradia), \
         patch("src.predict.openmeteo.fetch_forecast_max", return_value=33.0), \
         patch("src.predict._hora_local", return_value=10):
        predict.correr(hoy=hoy)

    preds = storage.read_predictions()
    assert len(preds) == 1
    fila = preds.iloc[0]
    assert fila["fecha_objetivo"] == "2026-06-16"
    assert fila["hora_decision"] == 10
    assert fila["p10"] <= fila["pico_pred"] <= fila["p90"]


def test_predict_fuera_de_franja_no_registra(tmp_path, monkeypatch):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PTF_MODEL_DIR", str(tmp_path))
    _sembrar_y_entrenar(tmp_path)
    hoy = date(2026, 6, 16)
    with patch("src.predict._hora_local", return_value=3):
        predict.correr(hoy=hoy)
    assert len(storage.read_predictions()) == 0
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `python -m pytest tests/test_predict.py -v`
Expected: FAIL (`ModuleNotFoundError: src.predict`)

- [ ] **Step 3: Implementar predict**

`src/predict.py`:
```python
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, evaluate, export, features, storage
from src.model import ModeloPico
from src.sources import openmeteo

RUTA_DATA_JSON = Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _hora_local(hoy: date) -> int:
    return datetime.now(ZoneInfo(config.TZ)).hour


def correr(hoy: date | None = None) -> None:
    hoy = hoy or datetime.now(ZoneInfo(config.TZ)).date()
    hora = _hora_local(hoy)

    # 1. Solo se predice dentro de la franja diurna de decisión.
    if hora not in config.HORAS_DECISION:
        return

    # 2. Intradía + forecast de hoy.
    intradia = pd.DataFrame(openmeteo.fetch_intradia(hoy))
    forecast_max = openmeteo.fetch_forecast_max(hoy)
    if len(intradia) == 0:
        return

    # 3. Features y predicción.
    fila = features.construir_fila(intradia, fecha=hoy.isoformat(),
                                   hora_h=hora, forecast_max=forecast_max)
    modelo = ModeloPico.cargar(config.ruta_modelo())
    p10, p50, p90 = modelo.predecir(fila)

    storage.append_prediction({
        "run_timestamp": datetime.now(ZoneInfo(config.TZ)).isoformat(timespec="seconds"),
        "fecha_objetivo": hoy.isoformat(),
        "hora_decision": hora,
        "pico_pred": p50,
        "p10": p10,
        "p90": p90,
        "modelo_version": config.MODELO_VERSION,
    })

    # 4. Evaluar días ya cerrados y exportar dashboard.
    predicciones = storage.read_predictions()
    observaciones = storage.read_observations()
    evaluacion = evaluate.evaluar(predicciones, observaciones)
    storage.write_evaluation(evaluacion)

    payload = export.construir_payload(predicciones, observaciones, evaluacion,
                                       hoy=hoy.isoformat())
    export.exportar(RUTA_DATA_JSON, payload)


if __name__ == "__main__":
    correr()
```

- [ ] **Step 4: Run test (debe pasar)**

Run: `python -m pytest tests/test_predict.py -v`
Expected: PASS

- [ ] **Step 5: Eliminar el pipeline viejo**

Borrar `src/pipeline.py` (vía MCP `delete_file`).

- [ ] **Step 6: Commit**

```bash
git add src/predict.py tests/test_predict.py
git rm src/pipeline.py
git commit -m "feat: corrida horaria predict.py; retira pipeline.py viejo"
```

---

## Task 14: Workflows de GitHub Actions

**Files:**
- Create: `.github/workflows/train.yml`
- Create: `.github/workflows/hourly.yml`
- Modify: `.github/workflows/backfill.yml`
- Delete: `.github/workflows/daily.yml`

- [ ] **Step 1: Crear `train.yml`**

`.github/workflows/train.yml`:
```yaml
name: Entrenamiento nocturno

on:
  schedule:
    - cron: "0 6 * * *"   # 06:00 UTC = 01:00 Panamá
  workflow_dispatch:

permissions:
  contents: write

jobs:
  train:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Instalar dependencias
        run: |
          pip install -r requirements.txt
          python -m playwright install chromium
      - name: Entrenar modelo
        env:
          WUNDERGROUND_API_KEY: ${{ secrets.WUNDERGROUND_API_KEY }}
        run: python -m src.train
      - name: Commit del modelo y datos
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ models/
          git commit -m "train: reentrenamiento $(date -u +%Y-%m-%d)" || echo "Sin cambios"
          git push
```

- [ ] **Step 2: Crear `hourly.yml`**

`.github/workflows/hourly.yml`:
```yaml
name: Predicción horaria

on:
  schedule:
    - cron: "0 11-21 * * *"   # 06:00–16:00 Panamá (UTC-5)
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  predict:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Instalar dependencias
        run: pip install -r requirements.txt
      - name: Predecir el pico de hoy
        run: python -m src.predict
      - name: Commit de la predicción
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ docs/data.json
          git commit -m "predict: $(date -u +%Y-%m-%dT%H:%M)" || echo "Sin cambios"
          git push

  deploy-pages:
    needs: predict
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: docs
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 3: Actualizar `backfill.yml`**

`.github/workflows/backfill.yml` (reemplazar el paso de ejecución para pasar la fecha):
```yaml
name: Backfill histórico

on:
  workflow_dispatch:
    inputs:
      desde:
        description: "Fecha inicial (YYYY-MM-DD)"
        default: "2020-01-01"

permissions:
  contents: write

jobs:
  backfill:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Instalar dependencias
        run: |
          pip install -r requirements.txt
          python -m playwright install chromium
      - name: Ejecutar backfill
        env:
          WUNDERGROUND_API_KEY: ${{ secrets.WUNDERGROUND_API_KEY }}
        run: python -m src.backfill "${{ github.event.inputs.desde }}"
      - name: Commit de datos
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git commit -m "data: backfill desde ${{ github.event.inputs.desde }}" || echo "Sin cambios"
          git push
```

- [ ] **Step 4: Eliminar `daily.yml`**

Borrar `.github/workflows/daily.yml` (vía MCP `delete_file`).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/train.yml .github/workflows/hourly.yml .github/workflows/backfill.yml
git rm .github/workflows/daily.yml
git commit -m "ci: workflows de entrenamiento nocturno y prediccion horaria"
```

---

## Task 15: Dashboard y README

**Files:**
- Modify: `docs/index.html` (y JS/CSS asociado en `docs/`)
- Modify: `README.md`

- [ ] **Step 1: Revisar el dashboard actual**

Leer `docs/index.html` (y los archivos JS/CSS que cargue) para conocer el estilo
y la librería de charts que ya usa.

- [ ] **Step 2: Adaptar el dashboard al nuevo `data.json`**

Actualizar `docs/index.html` (y su JS) para consumir el nuevo esquema:
- **Número grande:** `data.pico_hoy.pico_pred` con la banda
  `data.pico_hoy.p10`–`data.pico_hoy.p90` y la hora `data.pico_hoy.hora_decision`.
- **Curva de convergencia:** graficar `data.convergencia_hoy`
  (eje X = `hora_decision`, línea = `pico_pred`, área = `p10`–`p90`).
- **Precisión:** barra/línea de `data.error_por_hora`
  (eje X = `hora_decision`, Y = `error_medio_abs`).
- **Contexto:** `data.observados_recientes` para una mini-serie de picos reales.
- Quitar cualquier referencia al pronóstico de 7 días.

Mantener la misma librería de charts y la estética existente (ver Step 1).

- [ ] **Step 3: Actualizar README**

Reescribir `README.md` reflejando:
- Objetivo: predecir el pico de HOY, refinado cada hora.
- Modelo: LightGBM por cuantiles (p10/p50/p90).
- Fuentes: Open-Meteo (histórico/intradía/forecast) + Wunderground MPMG (pico real).
- Flujo: `train.yml` (nocturno) + `hourly.yml` (diurno cada hora) + `backfill.yml` (manual).
- Puesta en marcha: backfill primero, luego entrenamiento, luego la franja horaria corre sola.
- Desarrollo local: `pip install -r requirements.txt`, `python -m pytest -v`,
  `python -m src.backfill 2020-01-01`, `python -m src.train`, `python -m src.predict`.

- [ ] **Step 4: Verificar tests completos**

Run: `python -m pytest -v`
Expected: PASS (toda la suite)

- [ ] **Step 5: Commit**

```bash
git add docs/ README.md
git commit -m "feat: dashboard del pico de hoy + README actualizado"
```

---

## Task 16: Limpieza final y PR

- [ ] **Step 1: Verificar que no queden referencias muertas**

Buscar referencias a `src.pipeline`, `src.scraper`, `Climatologia`, `Predictor`,
`HORIZONTE_DIAS` en el repo. No deben existir.

- [ ] **Step 2: Suite completa verde**

Run: `python -m pytest -v`
Expected: PASS

- [ ] **Step 3: Abrir el PR**

Abrir PR de `ml-pico-diario` → `main` con resumen del cambio (migración a ML del
pico diario), enlazando el spec `docs/superpowers/specs/2026-06-16-ml-pico-diario-design.md`.

---

## Self-Review (cobertura del spec)

- **§1 Objetivo (pico de hoy + banda, refinado horario):** Tasks 8, 10, 13. ✔
- **§3 Roles de fuentes (Wunderground verdad / Open-Meteo motor):** Tasks 2–4, 11. ✔
- **§4 Formulación ML (set día×hora, sin leakage, cuantiles):** Tasks 6, 7, 8. ✔
- **§5 Arquitectura de ejecución (train nocturno / hourly diurno / backfill):** Tasks 12, 13, 14. ✔
- **§6 Datos (esquemas nuevos):** Tasks 1, 5. ✔
- **§7 Código (módulos):** Tasks 2–13. ✔
- **§8 Dashboard:** Task 15. ✔
- **§9 Dependencias (lightgbm):** Task 1. ✔
- **§11 Riesgos (forecast nullable, target MPMG):** Tasks 6, 7, 8. ✔

Sin placeholders pendientes. Nombres de funciones/columnas consistentes entre tasks
(`FEATURE_COLS`, `construir_fila`, `construir_set`, `ModeloPico.ajustar/predecir/guardar/cargar`,
`evaluar`, `construir_payload`, esquemas de `storage`).
