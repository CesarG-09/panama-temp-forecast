# panama-temp-forecast — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir un sistema que recolecta el máximo diario de temperatura de Ciudad de Panamá (estación MPMG) desde 2020, predice el máximo de los próximos 7 días con un modelo simple e intercambiable, verifica sus aciertos para retroalimentarse, y publica todo en un dashboard de GitHub Pages — orquestado por GitHub Actions.

**Architecture:** Pipeline por etapas (recolectar → evaluar → ajustar → predecir → exportar). Cada etapa es un módulo aislado con interfaz clara y testeable con fixtures. El almacenamiento son CSV versionados en git. El modelo vive detrás de una interfaz `ajustar/predecir` para poder sustituirlo sin tocar el resto.

**Tech Stack:** Python 3.12 · pandas · requests · BeautifulSoup + Playwright (respaldo de scraping) · pytest · GitHub Actions · GitHub Pages + Chart.js

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `src/__init__.py` | Marca el paquete |
| `src/config.py` | Constantes: estación, tz, horizonte, umbral, rutas vía `PTF_DATA_DIR` |
| `src/storage.py` | Lectura/escritura idempotente de los CSV (upsert por clave) |
| `src/scraper.py` | Obtención de datos: parseo JSON de la API + respaldo Playwright/HTML |
| `src/model.py` | `Climatologia` + `Predictor` (climatología + anomalía + corrección de sesgo) |
| `src/evaluate.py` | Comparación predicción vs observado + métricas |
| `src/export.py` | Construcción de `docs/data.json` para el dashboard |
| `src/pipeline.py` | Orquesta el flujo diario |
| `src/backfill.py` | Carga inicial del histórico desde 2020 (una vez) |
| `docs/index.html`, `docs/app.js` | Dashboard estático |
| `.github/workflows/daily.yml`, `backfill.yml` | Orquestación CI |
| `tests/...` | Tests con fixtures |

**Nota sobre la clave de API:** Wunderground sirve los datos vía `api.weather.com`, que exige un `apiKey` que la web embebe. No es secreto del usuario pero rota. Se captura una vez desde la pestaña *Network* del navegador (filtrar `historical.json`) y se guarda como **secret de GitHub** `WUNDERGROUND_API_KEY`. El parseo es 100% testeable con fixtures sin red.

---

## Task 1: Scaffolding del proyecto

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `tests/__init__.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Crear `requirements.txt`**

```
pandas==2.2.2
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2
playwright==1.44.0
pytest==8.2.2
```

- [ ] **Step 2: Crear `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 3: Crear paquetes vacíos**

`src/__init__.py` y `tests/__init__.py` con contenido vacío (un comentario):

```python
# paquete panama-temp-forecast
```

- [ ] **Step 4: Escribir el test de config**

`tests/test_config.py`:

```python
from datetime import date
from pathlib import Path
from src import config


def test_constantes_basicas():
    assert config.ESTACION == "MPMG:9:PA"
    assert config.TZ == "America/Panama"
    assert config.HORIZONTE_DIAS == 7
    assert config.UMBRAL_ACIERTO_C == 1.5
    assert config.FECHA_INICIO == date(2020, 1, 1)


def test_data_dir_respeta_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    assert config.data_dir() == tmp_path
    assert config.ruta_observaciones() == tmp_path / "observations.csv"
```

- [ ] **Step 5: Ejecutar el test y verificar que falla**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 6: Implementar `src/config.py`**

```python
import os
from datetime import date
from pathlib import Path

ESTACION = "MPMG:9:PA"
TZ = "America/Panama"
HORIZONTE_DIAS = 7
UMBRAL_ACIERTO_C = 1.5
FECHA_INICIO = date(2020, 1, 1)
MODELO_VERSION = "clima-v1"

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def data_dir() -> Path:
    return Path(os.environ.get("PTF_DATA_DIR", _DEFAULT_DATA_DIR))


def ruta_observaciones() -> Path:
    return data_dir() / "observations.csv"


def ruta_predicciones() -> Path:
    return data_dir() / "predictions.csv"


def ruta_evaluacion() -> Path:
    return data_dir() / "evaluation.csv"
```

- [ ] **Step 7: Ejecutar el test y verificar que pasa**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini src/ tests/
git commit -m "chore: scaffolding y configuración base"
```

---

## Task 2: Storage — upsert idempotente de CSV

**Files:**
- Create: `src/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Escribir el test**

`tests/test_storage.py`:

```python
import pandas as pd
from src import storage


def test_upsert_crea_y_actualiza_sin_duplicar(tmp_path):
    ruta = tmp_path / "obs.csv"
    cols = ["fecha", "temp_max_c"]

    storage.upsert_rows(ruta, [{"fecha": "2020-01-01", "temp_max_c": 31.0}], cols, ["fecha"])
    df = storage.upsert_rows(ruta, [{"fecha": "2020-01-01", "temp_max_c": 32.5}], cols, ["fecha"])

    assert len(df) == 1
    assert df.iloc[0]["temp_max_c"] == 32.5


def test_upsert_ordena_por_clave(tmp_path):
    ruta = tmp_path / "obs.csv"
    cols = ["fecha", "temp_max_c"]
    storage.upsert_rows(ruta, [
        {"fecha": "2020-01-03", "temp_max_c": 33.0},
        {"fecha": "2020-01-01", "temp_max_c": 31.0},
    ], cols, ["fecha"])
    df = storage.read_csv(ruta, cols)
    assert list(df["fecha"]) == ["2020-01-01", "2020-01-03"]


def test_read_csv_vacio_devuelve_columnas(tmp_path):
    df = storage.read_csv(tmp_path / "no_existe.csv", ["fecha", "temp_max_c"])
    assert list(df.columns) == ["fecha", "temp_max_c"]
    assert len(df) == 0
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.storage'`

- [ ] **Step 3: Implementar `src/storage.py`**

```python
from pathlib import Path

import pandas as pd

from src import config


def read_csv(ruta: Path, columnas: list[str]) -> pd.DataFrame:
    if Path(ruta).exists():
        return pd.read_csv(ruta, dtype={"fecha": str, "fecha_objetivo": str,
                                        "fecha_prediccion": str})
    return pd.DataFrame(columns=columnas)


def upsert_rows(ruta: Path, filas: list[dict], columnas: list[str],
                claves: list[str]) -> pd.DataFrame:
    ruta = Path(ruta)
    nuevo = pd.DataFrame(filas, columns=columnas)
    if ruta.exists():
        df = pd.concat([read_csv(ruta, columnas), nuevo], ignore_index=True)
    else:
        df = nuevo
    df = (df.drop_duplicates(subset=claves, keep="last")
            .sort_values(claves)
            .reset_index(drop=True))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
    return df


OBS_COLS = ["fecha", "temp_max_c"]
PRED_COLS = ["fecha_prediccion", "fecha_objetivo", "temp_max_pred_c", "modelo_version"]
EVAL_COLS = ["fecha_objetivo", "pred_c", "real_c", "error_c", "acierto"]


def read_observations() -> pd.DataFrame:
    return read_csv(config.ruta_observaciones(), OBS_COLS)


def upsert_observations(filas: list[dict]) -> pd.DataFrame:
    return upsert_rows(config.ruta_observaciones(), filas, OBS_COLS, ["fecha"])


def read_predictions() -> pd.DataFrame:
    return read_csv(config.ruta_predicciones(), PRED_COLS)


def upsert_predictions(filas: list[dict]) -> pd.DataFrame:
    return upsert_rows(config.ruta_predicciones(), filas, PRED_COLS,
                       ["fecha_prediccion", "fecha_objetivo"])


def write_evaluation(df: pd.DataFrame) -> None:
    ruta = config.ruta_evaluacion()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)


def read_evaluation() -> pd.DataFrame:
    return read_csv(config.ruta_evaluacion(), EVAL_COLS)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_storage.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/storage.py tests/test_storage.py
git commit -m "feat: storage con upsert idempotente de CSV"
```

---

## Task 3: Scraper — parseo del JSON histórico

**Files:**
- Create: `src/scraper.py`
- Create: `tests/fixtures/historical_sample.json`
- Test: `tests/test_scraper_parse.py`

- [ ] **Step 1: Crear el fixture JSON**

`tests/fixtures/historical_sample.json` (dos días; `valid_time_gmt` en epoch segundos UTC, `temp` en °C porque pediremos `units=m`):

```json
{
  "observations": [
    {"valid_time_gmt": 1577880000, "temp": 26.0},
    {"valid_time_gmt": 1577905200, "temp": 31.5},
    {"valid_time_gmt": 1577919600, "temp": 29.0},
    {"valid_time_gmt": 1577966400, "temp": 27.0},
    {"valid_time_gmt": 1577991600, "temp": 33.2},
    {"valid_time_gmt": 1578006000, "temp": null}
  ]
}
```

- [ ] **Step 2: Escribir el test**

`tests/test_scraper_parse.py`:

```python
import json
from pathlib import Path

from src import scraper

FIXTURE = Path(__file__).parent / "fixtures" / "historical_sample.json"


def test_parse_agrupa_por_dia_y_toma_el_maximo():
    payload = json.loads(FIXTURE.read_text())
    filas = scraper.parse_historical_json(payload)

    # Epochs caen el 2020-01-01 y 2020-01-02 en hora de Panamá (UTC-5)
    assert filas == [
        {"fecha": "2020-01-01", "temp_max_c": 31.5},
        {"fecha": "2020-01-02", "temp_max_c": 33.2},
    ]


def test_parse_ignora_temperaturas_nulas_y_payload_vacio():
    assert scraper.parse_historical_json({"observations": []}) == []
    assert scraper.parse_historical_json({}) == []
```

- [ ] **Step 3: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_scraper_parse.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.scraper'`

- [ ] **Step 4: Implementar el parseo en `src/scraper.py`**

```python
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from src import config


def parse_historical_json(payload: dict) -> list[dict]:
    """Agrupa observaciones por día (hora local de Panamá) y toma el máximo."""
    tz = ZoneInfo(config.TZ)
    por_dia: dict = defaultdict(list)
    for obs in payload.get("observations", []):
        temp = obs.get("temp")
        ts = obs.get("valid_time_gmt")
        if temp is None or ts is None:
            continue
        dia = datetime.fromtimestamp(ts, tz=tz).date()
        por_dia[dia].append(temp)
    return [
        {"fecha": dia.isoformat(), "temp_max_c": round(max(temps), 1)}
        for dia, temps in sorted(por_dia.items())
    ]
```

- [ ] **Step 5: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_scraper_parse.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/scraper.py tests/fixtures/historical_sample.json tests/test_scraper_parse.py
git commit -m "feat: parseo del JSON histórico de Wunderground"
```

---

## Task 4: Scraper — fetch por API con manejo de errores

**Files:**
- Modify: `src/scraper.py`
- Test: `tests/test_scraper_fetch.py`

- [ ] **Step 1: Escribir el test (mock de `requests.get`)**

`tests/test_scraper_fetch.py`:

```python
import json
from datetime import date
from pathlib import Path

import pytest

from src import scraper

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "historical_sample.json").read_text())


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_via_api_construye_url_y_parsea(monkeypatch):
    capturado = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        capturado["url"] = url
        capturado["params"] = params
        return _FakeResp(FIXTURE)

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    monkeypatch.setenv("WUNDERGROUND_API_KEY", "clave-de-prueba")

    filas = scraper.fetch_via_api(date(2020, 1, 1), date(2020, 1, 2))

    assert capturado["params"]["apiKey"] == "clave-de-prueba"
    assert capturado["params"]["startDate"] == "20200101"
    assert capturado["params"]["endDate"] == "20200102"
    assert capturado["params"]["units"] == "m"
    assert filas[0] == {"fecha": "2020-01-01", "temp_max_c": 31.5}


def test_fetch_via_api_sin_clave_lanza(monkeypatch):
    monkeypatch.delenv("WUNDERGROUND_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="WUNDERGROUND_API_KEY"):
        scraper.fetch_via_api(date(2020, 1, 1), date(2020, 1, 2))
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_scraper_fetch.py -v`
Expected: FAIL con `AttributeError: module 'src.scraper' has no attribute 'requests'`

- [ ] **Step 3: Implementar `fetch_via_api` en `src/scraper.py`**

Añadir al inicio de `src/scraper.py` (junto a los imports existentes):

```python
import os

import requests

API_URL = "https://api.weather.com/v1/location/{station}/observations/historical.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (panama-temp-forecast)"}
_TIMEOUT = 30
```

Y añadir la función:

```python
def fetch_via_api(desde, hasta) -> list[dict]:
    """Obtiene observaciones del rango [desde, hasta] vía la API de Weather.com."""
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
    return parse_historical_json(resp.json())
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_scraper_fetch.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/scraper.py tests/test_scraper_fetch.py
git commit -m "feat: fetch de observaciones vía API de Weather.com"
```

---

## Task 5: Scraper — respaldo Playwright + parseo de HTML

**Files:**
- Modify: `src/scraper.py`
- Create: `tests/fixtures/history_page.html`
- Test: `tests/test_scraper_fallback.py`

- [ ] **Step 1: Crear el fixture HTML**

`tests/fixtures/history_page.html` (recorte representativo de la tabla "Daily Observations" con el valor "High" en °F que la web muestra por defecto):

```html
<table class="days">
  <tbody>
    <tr>
      <td>High Temp</td>
      <td><span class="wu-value wu-value-to">92</span><span> &deg;F</span></td>
    </tr>
  </tbody>
</table>
```

- [ ] **Step 2: Escribir el test**

`tests/test_scraper_fallback.py`:

```python
from datetime import date
from pathlib import Path

from src import scraper

HTML = (Path(__file__).parent / "fixtures" / "history_page.html").read_text()


def test_parse_history_html_devuelve_maximo_en_celsius():
    fecha = date(2020, 1, 1)
    fila = scraper.parse_history_html(HTML, fecha)
    # 92 °F = 33.3 °C
    assert fila == {"fecha": "2020-01-01", "temp_max_c": 33.3}


def test_f_a_c():
    assert scraper.f_a_c(32) == 0.0
    assert scraper.f_a_c(212) == 100.0
```

- [ ] **Step 3: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_scraper_fallback.py -v`
Expected: FAIL con `AttributeError: module 'src.scraper' has no attribute 'parse_history_html'`

- [ ] **Step 4: Implementar el parseo de HTML y el orquestador en `src/scraper.py`**

Añadir import al inicio:

```python
from bs4 import BeautifulSoup
```

Añadir funciones:

```python
def f_a_c(f: float) -> float:
    return round((f - 32) * 5 / 9, 1)


def parse_history_html(html: str, fecha) -> dict:
    """Extrae la temperatura máxima (°F en la web) de la página de historial diario."""
    soup = BeautifulSoup(html, "lxml")
    for tr in soup.select("tr"):
        celdas = tr.find_all("td")
        if celdas and "High Temp" in celdas[0].get_text():
            valor = tr.select_one(".wu-value")
            f = float(valor.get_text().strip())
            return {"fecha": fecha.isoformat(), "temp_max_c": f_a_c(f)}
    raise ValueError("No se encontró 'High Temp' en el HTML")


def fetch_via_browser(fecha) -> list[dict]:
    """Respaldo: abre la página real en Playwright y lee la máxima del día.

    Requiere `playwright install chromium`. Se usa solo si la API falla.
    """
    from playwright.sync_api import sync_playwright

    url = (f"https://www.wunderground.com/history/daily/pa/panama-city/MPMG/"
           f"date/{fecha.isoformat()}")
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(user_agent=_HEADERS["User-Agent"])
        pagina.goto(url, wait_until="networkidle", timeout=60000)
        pagina.wait_for_selector("table.days", timeout=30000)
        html = pagina.content()
        navegador.close()
    return [parse_history_html(html, fecha)]
```

- [ ] **Step 5: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_scraper_fallback.py -v`
Expected: PASS (2 passed). (Los tests sólo ejercitan el parseo; `fetch_via_browser` no se invoca.)

- [ ] **Step 6: Commit**

```bash
git add src/scraper.py tests/fixtures/history_page.html tests/test_scraper_fallback.py
git commit -m "feat: respaldo Playwright y parseo de HTML del historial"
```

---

## Task 6: Scraper — orquestador con respaldo

**Files:**
- Modify: `src/scraper.py`
- Test: `tests/test_scraper_orquestador.py`

- [ ] **Step 1: Escribir el test**

`tests/test_scraper_orquestador.py`:

```python
from datetime import date

from src import scraper


def test_obtener_usa_api_cuando_funciona(monkeypatch):
    monkeypatch.setattr(scraper, "fetch_via_api",
                        lambda d, h: [{"fecha": "2020-01-01", "temp_max_c": 31.5}])
    llamado = {"browser": False}
    monkeypatch.setattr(scraper, "fetch_via_browser",
                        lambda f: llamado.__setitem__("browser", True) or [])

    filas = scraper.obtener_observaciones(date(2020, 1, 1), date(2020, 1, 1))

    assert filas == [{"fecha": "2020-01-01", "temp_max_c": 31.5}]
    assert llamado["browser"] is False


def test_obtener_cae_a_browser_si_api_falla(monkeypatch):
    def api_rota(d, h):
        raise RuntimeError("api caída")

    monkeypatch.setattr(scraper, "fetch_via_api", api_rota)
    monkeypatch.setattr(scraper, "fetch_via_browser",
                        lambda f: [{"fecha": f.isoformat(), "temp_max_c": 33.3}])

    filas = scraper.obtener_observaciones(date(2020, 1, 1), date(2020, 1, 2))

    assert {"fecha": "2020-01-01", "temp_max_c": 33.3} in filas
    assert {"fecha": "2020-01-02", "temp_max_c": 33.3} in filas
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_scraper_orquestador.py -v`
Expected: FAIL con `AttributeError: module 'src.scraper' has no attribute 'obtener_observaciones'`

- [ ] **Step 3: Implementar `obtener_observaciones` en `src/scraper.py`**

Añadir import al inicio:

```python
from datetime import timedelta
```

Añadir función:

```python
def obtener_observaciones(desde, hasta) -> list[dict]:
    """Intenta la API; si falla, cae al navegador día por día."""
    try:
        return fetch_via_api(desde, hasta)
    except Exception:
        filas: list[dict] = []
        dia = desde
        while dia <= hasta:
            try:
                filas.extend(fetch_via_browser(dia))
            except Exception:
                pass  # día sin dato: se omite, queda como hueco
            dia += timedelta(days=1)
        return filas
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_scraper_orquestador.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/scraper.py tests/test_scraper_orquestador.py
git commit -m "feat: orquestador de scraping con respaldo a navegador"
```

---

## Task 7: Modelo — climatología base

**Files:**
- Create: `src/model.py`
- Test: `tests/test_model_climatologia.py`

- [ ] **Step 1: Escribir el test**

`tests/test_model_climatologia.py`:

```python
import pandas as pd

from src.model import Climatologia


def _hist_constante(valor, dias=400):
    fechas = pd.date_range("2020-01-01", periods=dias, freq="D")
    return pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"),
                         "temp_max_c": [valor] * dias})


def test_climatologia_predice_la_media_del_dia_del_anio():
    hist = _hist_constante(30.0)
    modelo = Climatologia().ajustar(hist)
    assert modelo.predecir(["2021-06-01"])[0] == 30.0


def test_climatologia_captura_estacionalidad():
    # Enero frío (28), julio caluroso (34)
    fechas = pd.date_range("2020-01-01", periods=730, freq="D")
    temps = [28.0 if f.month in (12, 1, 2) else 34.0 for f in fechas]
    hist = pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"), "temp_max_c": temps})
    modelo = Climatologia(ventana_dias=7).ajustar(hist)
    enero = modelo.predecir(["2021-01-15"])[0]
    julio = modelo.predecir(["2021-07-15"])[0]
    assert enero < 30.0
    assert julio > 32.0
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_model_climatologia.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.model'`

- [ ] **Step 3: Implementar `Climatologia` en `src/model.py`**

```python
import pandas as pd


class Climatologia:
    """Media del máximo para cada día-del-año, con ventana circular ±N días."""

    def __init__(self, ventana_dias: int = 7):
        self.ventana = ventana_dias
        self._hist: pd.DataFrame | None = None
        self._media_global: float = 0.0

    def ajustar(self, hist: pd.DataFrame) -> "Climatologia":
        df = hist.copy()
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["doy"] = df["fecha"].dt.dayofyear
        self._hist = df
        self._media_global = float(df["temp_max_c"].mean())
        return self

    def _media_doy(self, doy: int) -> float:
        difs = ((self._hist["doy"] - doy + 182) % 365) - 182
        vals = self._hist.loc[difs.abs() <= self.ventana, "temp_max_c"]
        if len(vals) == 0:
            return self._media_global
        return float(vals.mean())

    def predecir(self, fechas) -> list[float]:
        return [round(self._media_doy(pd.Timestamp(f).dayofyear), 1) for f in fechas]
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_model_climatologia.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/model.py tests/test_model_climatologia.py
git commit -m "feat: modelo de climatología base por día del año"
```

---

## Task 8: Modelo — Predictor con anomalía y corrección de sesgo

**Files:**
- Modify: `src/model.py`
- Test: `tests/test_model_predictor.py`

- [ ] **Step 1: Escribir el test**

`tests/test_model_predictor.py`:

```python
import pandas as pd

from src.model import Predictor


def _hist_constante(valor, dias=400):
    fechas = pd.date_range("2020-01-01", periods=dias, freq="D")
    return pd.DataFrame({"fecha": fechas.strftime("%Y-%m-%d"),
                         "temp_max_c": [valor] * dias})


def test_predictor_sin_anomalia_ni_sesgo_es_climatologia():
    hist = _hist_constante(30.0)
    pred = Predictor().ajustar(hist)
    assert pred.predecir(["2021-06-01"]) == [30.0]


def test_anomalia_reciente_desplaza_la_prediccion():
    hist = _hist_constante(30.0, dias=400)
    hist.loc[hist.index[-3:], "temp_max_c"] = 33.0  # últimos 3 días más calientes
    pred = Predictor(dias_anomalia=3).ajustar(hist)
    assert pred.predecir(["2021-06-01"])[0] > 30.0


def test_correccion_de_sesgo_reduce_sobreprediccion():
    hist = _hist_constante(30.0)
    # El modelo venía prediciendo 2 °C de más (error_c = pred - real = +2)
    evaluacion = pd.DataFrame({
        "fecha_objetivo": ["2021-05-29", "2021-05-30", "2021-05-31"],
        "pred_c": [32.0, 32.0, 32.0],
        "real_c": [30.0, 30.0, 30.0],
        "error_c": [2.0, 2.0, 2.0],
        "acierto": [False, False, False],
    })
    pred = Predictor().ajustar(hist, evaluacion)
    # Se corrige hacia abajo ~2 °C respecto a la climatología (30.0)
    assert pred.predecir(["2021-06-01"])[0] == 28.0
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_model_predictor.py -v`
Expected: FAIL con `ImportError: cannot import name 'Predictor'`

- [ ] **Step 3: Implementar `Predictor` en `src/model.py`**

Añadir al final de `src/model.py`:

```python
class Predictor:
    """Climatología + anomalía reciente + corrección de sesgo (lazo de mejora)."""

    def __init__(self, clima: Climatologia | None = None,
                 dias_anomalia: int = 3, dias_sesgo: int = 14):
        self.clima = clima or Climatologia()
        self.dias_anomalia = dias_anomalia
        self.dias_sesgo = dias_sesgo
        self.anomalia = 0.0
        self.sesgo = 0.0

    def ajustar(self, hist: pd.DataFrame, evaluacion: pd.DataFrame | None = None):
        self.clima.ajustar(hist)

        h = hist.copy()
        h["fecha"] = pd.to_datetime(h["fecha"])
        h = h.sort_values("fecha")
        ult = h.tail(self.dias_anomalia)
        if len(ult):
            base = self.clima.predecir(ult["fecha"].tolist())
            self.anomalia = float((ult["temp_max_c"].to_numpy() - base).mean())

        if evaluacion is not None and len(evaluacion):
            self.sesgo = float(evaluacion.tail(self.dias_sesgo)["error_c"].mean())

        return self

    def predecir(self, fechas) -> list[float]:
        base = self.clima.predecir(fechas)
        return [round(b + self.anomalia - self.sesgo, 1) for b in base]
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_model_predictor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/model.py tests/test_model_predictor.py
git commit -m "feat: Predictor con anomalía reciente y corrección de sesgo"
```

---

## Task 9: Evaluación — aciertos y métricas

**Files:**
- Create: `src/evaluate.py`
- Test: `tests/test_evaluate.py`

- [ ] **Step 1: Escribir el test**

`tests/test_evaluate.py`:

```python
import pandas as pd

from src import evaluate


def _predicciones():
    return pd.DataFrame({
        "fecha_prediccion": ["2021-05-30", "2021-05-31", "2021-05-30"],
        "fecha_objetivo": ["2021-06-01", "2021-06-01", "2021-06-02"],
        "temp_max_pred_c": [31.0, 30.5, 35.0],
        "modelo_version": ["clima-v1"] * 3,
    })


def _observaciones():
    return pd.DataFrame({"fecha": ["2021-06-01"], "temp_max_c": [30.0]})


def test_evaluar_usa_la_prediccion_mas_reciente_por_objetivo():
    ev = evaluate.evaluar(_predicciones(), _observaciones(), umbral=1.5)
    # Sólo 2021-06-01 tiene observación; gana la predicción del 2021-05-31 (30.5)
    assert len(ev) == 1
    fila = ev.iloc[0]
    assert fila["fecha_objetivo"] == "2021-06-01"
    assert fila["pred_c"] == 30.5
    assert fila["real_c"] == 30.0
    assert fila["error_c"] == 0.5
    assert bool(fila["acierto"]) is True


def test_evaluar_marca_fallo_fuera_de_umbral():
    preds = pd.DataFrame({
        "fecha_prediccion": ["2021-05-31"], "fecha_objetivo": ["2021-06-01"],
        "temp_max_pred_c": [33.0], "modelo_version": ["clima-v1"],
    })
    ev = evaluate.evaluar(preds, _observaciones(), umbral=1.5)
    assert bool(ev.iloc[0]["acierto"]) is False


def test_metricas_agrega_mae_y_aciertos():
    ev = pd.DataFrame({
        "fecha_objetivo": ["a", "b", "c", "d"],
        "pred_c": [0, 0, 0, 0], "real_c": [0, 0, 0, 0],
        "error_c": [1.0, -1.0, 2.0, -2.0],
        "acierto": [True, True, False, False],
    })
    m = evaluate.metricas(ev)
    assert m["n"] == 4
    assert m["mae"] == 1.5
    assert m["aciertos_pct"] == 50.0


def test_metricas_vacio():
    m = evaluate.metricas(pd.DataFrame(columns=["error_c", "acierto"]))
    assert m == {"n": 0, "mae": None, "aciertos_pct": None}
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_evaluate.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.evaluate'`

- [ ] **Step 3: Implementar `src/evaluate.py`**

```python
import pandas as pd

from src import config

COLS = ["fecha_objetivo", "pred_c", "real_c", "error_c", "acierto"]


def evaluar(predicciones: pd.DataFrame, observaciones: pd.DataFrame,
            umbral: float = config.UMBRAL_ACIERTO_C) -> pd.DataFrame:
    obs = dict(zip(observaciones["fecha"], observaciones["temp_max_c"]))
    filas = []
    for fobj, grp in predicciones.groupby("fecha_objetivo"):
        if fobj not in obs:
            continue
        reciente = grp.sort_values("fecha_prediccion").iloc[-1]
        pred = float(reciente["temp_max_pred_c"])
        real = float(obs[fobj])
        error = round(pred - real, 1)
        filas.append({
            "fecha_objetivo": fobj, "pred_c": pred, "real_c": real,
            "error_c": error, "acierto": abs(error) <= umbral,
        })
    return pd.DataFrame(filas, columns=COLS).sort_values("fecha_objetivo").reset_index(drop=True)


def metricas(evaluacion: pd.DataFrame) -> dict:
    if len(evaluacion) == 0:
        return {"n": 0, "mae": None, "aciertos_pct": None}
    return {
        "n": int(len(evaluacion)),
        "mae": round(float(evaluacion["error_c"].abs().mean()), 2),
        "aciertos_pct": round(100 * float(evaluacion["acierto"].mean()), 1),
    }
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_evaluate.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/evaluate.py tests/test_evaluate.py
git commit -m "feat: evaluación de aciertos y métricas del modelo"
```

---

## Task 10: Export — construir data.json

**Files:**
- Create: `src/export.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Escribir el test**

`tests/test_export.py`:

```python
import json

import pandas as pd

from src import export


def test_construir_payload_tiene_secciones_esperadas():
    observaciones = pd.DataFrame({"fecha": ["2021-05-31"], "temp_max_c": [30.0]})
    predicciones = pd.DataFrame({
        "fecha_prediccion": ["2021-05-31"], "fecha_objetivo": ["2021-06-01"],
        "temp_max_pred_c": [31.0], "modelo_version": ["clima-v1"],
    })
    evaluacion = pd.DataFrame({
        "fecha_objetivo": ["2021-05-31"], "pred_c": [29.5], "real_c": [30.0],
        "error_c": [-0.5], "acierto": [True],
    })

    payload = export.construir_payload(observaciones, predicciones, evaluacion, hoy="2021-05-31")

    assert payload["historico"] == [{"fecha": "2021-05-31", "temp_max_c": 30.0}]
    assert payload["predicciones"] == [{"fecha_objetivo": "2021-06-01", "temp_max_pred_c": 31.0}]
    assert payload["metricas"]["aciertos_pct"] == 100.0
    assert "generado" in payload


def test_exportar_escribe_json(tmp_path):
    ruta = tmp_path / "data.json"
    export.exportar(ruta, {"historico": [], "predicciones": [], "metricas": {},
                          "evaluaciones": [], "generado": "x"})
    datos = json.loads(ruta.read_text())
    assert datos["generado"] == "x"
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_export.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.export'`

- [ ] **Step 3: Implementar `src/export.py`**

```python
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, evaluate


def construir_payload(observaciones: pd.DataFrame, predicciones: pd.DataFrame,
                      evaluacion: pd.DataFrame, hoy: str) -> dict:
    futuras = predicciones[predicciones["fecha_objetivo"] > hoy]
    futuras = (futuras.sort_values("fecha_prediccion")
                      .drop_duplicates("fecha_objetivo", keep="last")
                      .sort_values("fecha_objetivo"))
    return {
        "generado": datetime.now(ZoneInfo(config.TZ)).isoformat(),
        "historico": observaciones.sort_values("fecha").to_dict("records"),
        "predicciones": futuras[["fecha_objetivo", "temp_max_pred_c"]].to_dict("records"),
        "metricas": evaluate.metricas(evaluacion),
        "evaluaciones": evaluacion.sort_values("fecha_objetivo").tail(30).to_dict("records"),
    }


def exportar(ruta: Path, payload: dict) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_export.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/export.py tests/test_export.py
git commit -m "feat: exportación de data.json para el dashboard"
```

---

## Task 11: Pipeline — orquestación del flujo diario

**Files:**
- Create: `src/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Escribir el test (con fetch falso y data dir temporal)**

`tests/test_pipeline.py`:

```python
from datetime import date

import pandas as pd

from src import pipeline, storage


def test_pipeline_recolecta_evalua_y_predice(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))

    # Histórico previo: 400 días constantes a 30 °C terminando el 2021-05-31
    fechas = pd.date_range(end="2021-05-31", periods=400, freq="D")
    storage.upsert_observations(
        [{"fecha": f.strftime("%Y-%m-%d"), "temp_max_c": 30.0} for f in fechas])

    # El scraper "trae" el día 2021-06-01 observado a 30 °C
    def fake_fetch(desde, hasta):
        return [{"fecha": "2021-06-01", "temp_max_c": 30.0}]

    monkeypatch.setattr(pipeline.scraper, "obtener_observaciones", fake_fetch)

    pipeline.correr(hoy=date(2021, 6, 1))

    preds = storage.read_predictions()
    # Se generaron 7 predicciones futuras (objetivo 06-02 .. 06-08)
    futuras = preds[preds["fecha_objetivo"] > "2021-06-01"]
    assert len(futuras) == 7
    # data.json fue escrito
    assert (tmp_path.parent / "docs" / "data.json").exists() or \
           (tmp_path / "data.json").exists() or pipeline.RUTA_DATA_JSON.exists()


def test_pipeline_es_idempotente(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))
    fechas = pd.date_range(end="2021-05-31", periods=400, freq="D")
    storage.upsert_observations(
        [{"fecha": f.strftime("%Y-%m-%d"), "temp_max_c": 30.0} for f in fechas])
    monkeypatch.setattr(pipeline.scraper, "obtener_observaciones",
                        lambda d, h: [{"fecha": "2021-06-01", "temp_max_c": 30.0}])

    pipeline.correr(hoy=date(2021, 6, 1))
    n1 = len(storage.read_predictions())
    pipeline.correr(hoy=date(2021, 6, 1))
    n2 = len(storage.read_predictions())
    assert n1 == n2  # re-correr el mismo día no duplica
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.pipeline'`

- [ ] **Step 3: Implementar `src/pipeline.py`**

```python
from datetime import date, timedelta
from pathlib import Path

from src import config, evaluate, export, scraper, storage
from src.model import Predictor

RUTA_DATA_JSON = Path(__file__).resolve().parent.parent / "docs" / "data.json"


def _ultima_fecha(observaciones) -> date:
    if len(observaciones) == 0:
        return config.FECHA_INICIO
    return date.fromisoformat(observaciones["fecha"].max())


def correr(hoy: date | None = None) -> None:
    hoy = hoy or date.today()

    # 1. Recolectar desde el día siguiente al último observado hasta ayer
    observaciones = storage.read_observations()
    desde = _ultima_fecha(observaciones) + timedelta(days=1)
    hasta = hoy - timedelta(days=1)
    if desde <= hasta:
        nuevos = scraper.obtener_observaciones(desde, hasta)
        if nuevos:
            storage.upsert_observations(nuevos)
            observaciones = storage.read_observations()

    # 2. Evaluar predicciones pasadas contra lo observado
    predicciones = storage.read_predictions()
    evaluacion = evaluate.evaluar(predicciones, observaciones)
    storage.write_evaluation(evaluacion)

    # 3. Ajustar el modelo y predecir el horizonte
    modelo = Predictor().ajustar(observaciones, evaluacion)
    fechas_fut = [hoy + timedelta(days=i) for i in range(1, config.HORIZONTE_DIAS + 1)]
    valores = modelo.predecir(fechas_fut)
    filas = [{
        "fecha_prediccion": hoy.isoformat(),
        "fecha_objetivo": f.isoformat(),
        "temp_max_pred_c": v,
        "modelo_version": config.MODELO_VERSION,
    } for f, v in zip(fechas_fut, valores)]
    storage.upsert_predictions(filas)
    predicciones = storage.read_predictions()

    # 4. Exportar para el dashboard
    payload = export.construir_payload(observaciones, predicciones, evaluacion,
                                       hoy=hoy.isoformat())
    export.exportar(RUTA_DATA_JSON, payload)


if __name__ == "__main__":
    correr()
```

- [ ] **Step 4: Ajustar la aserción del test a `RUTA_DATA_JSON`**

En `tests/test_pipeline.py`, reemplazar el bloque `assert (tmp_path.parent ...` por:

```python
    assert pipeline.RUTA_DATA_JSON.exists()
```

- [ ] **Step 5: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Ejecutar toda la suite**

Run: `python -m pytest -v`
Expected: PASS (todos los tests verdes)

- [ ] **Step 7: Commit**

```bash
git add src/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline de orquestación del flujo diario"
```

---

## Task 12: Backfill — carga inicial desde 2020

**Files:**
- Create: `src/backfill.py`
- Test: `tests/test_backfill.py`

- [ ] **Step 1: Escribir el test**

`tests/test_backfill.py`:

```python
from datetime import date

from src import backfill


def test_rangos_mensuales_cubre_desde_hasta():
    rangos = backfill.rangos_mensuales(date(2020, 1, 1), date(2020, 3, 15))
    assert rangos[0] == (date(2020, 1, 1), date(2020, 1, 31))
    assert rangos[1] == (date(2020, 2, 1), date(2020, 2, 29))  # 2020 bisiesto
    assert rangos[-1] == (date(2020, 3, 1), date(2020, 3, 15))


def test_correr_backfill_acumula_observaciones(monkeypatch, tmp_path):
    monkeypatch.setenv("PTF_DATA_DIR", str(tmp_path))

    def fake_fetch(desde, hasta):
        return [{"fecha": desde.isoformat(), "temp_max_c": 31.0}]

    monkeypatch.setattr(backfill.scraper, "obtener_observaciones", fake_fetch)

    backfill.correr(date(2020, 1, 1), date(2020, 3, 15))

    from src import storage
    obs = storage.read_observations()
    assert len(obs) == 3  # un dato por cada rango mensual (fixture simplificado)
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.backfill'`

- [ ] **Step 3: Implementar `src/backfill.py`**

```python
import calendar
from datetime import date

from src import config, scraper, storage


def rangos_mensuales(desde: date, hasta: date) -> list[tuple[date, date]]:
    rangos = []
    cursor = desde
    while cursor <= hasta:
        ultimo_dia = calendar.monthrange(cursor.year, cursor.month)[1]
        fin_mes = date(cursor.year, cursor.month, ultimo_dia)
        rangos.append((cursor, min(fin_mes, hasta)))
        cursor = fin_mes.replace(day=ultimo_dia)
        cursor = date(cursor.year + (cursor.month // 12),
                      (cursor.month % 12) + 1, 1)
    return rangos


def correr(desde: date | None = None, hasta: date | None = None) -> None:
    desde = desde or config.FECHA_INICIO
    hasta = hasta or date.today()
    for ini, fin in rangos_mensuales(desde, hasta):
        filas = scraper.obtener_observaciones(ini, fin)
        if filas:
            storage.upsert_observations(filas)
        print(f"Backfill {ini}..{fin}: {len(filas)} días")


if __name__ == "__main__":
    correr()
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/backfill.py tests/test_backfill.py
git commit -m "feat: backfill mensual del histórico desde 2020"
```

---

## Task 13: Dashboard — index.html + app.js

**Files:**
- Create: `docs/index.html`
- Create: `docs/app.js`
- Create: `docs/.nojekyll`

- [ ] **Step 1: Crear `docs/.nojekyll`** (archivo vacío; evita que Pages procese con Jekyll)

```
```

- [ ] **Step 2: Crear `docs/index.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Temperatura máxima — Ciudad de Panamá</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.5rem; }
    .metricas { display: flex; gap: 1.5rem; margin: 1rem 0; flex-wrap: wrap; }
    .card { background: #f4f6f8; border-radius: 10px; padding: 1rem 1.25rem; }
    .card .valor { font-size: 1.6rem; font-weight: 700; }
    .card .etiqueta { font-size: .8rem; color: #555; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { border-bottom: 1px solid #e2e2e2; padding: .5rem; text-align: left; font-size: .9rem; }
    .ok { color: #1a7f37; } .fail { color: #cf222e; }
    footer { margin-top: 2rem; font-size: .8rem; color: #888; }
  </style>
</head>
<body>
  <h1>🌡️ Temperatura máxima — Ciudad de Panamá (MPMG)</h1>
  <p>Predicción propia del máximo diario, con verificación de aciertos para retroalimentar el modelo.</p>

  <div class="metricas" id="metricas"></div>
  <canvas id="grafica" height="120"></canvas>

  <h2>Últimas verificaciones</h2>
  <table id="tabla">
    <thead><tr><th>Fecha objetivo</th><th>Predicho</th><th>Real</th><th>Error</th><th>Veredicto</th></tr></thead>
    <tbody></tbody>
  </table>

  <footer>Generado: <span id="generado"></span> · Datos: Wunderground / Weather.com</footer>
  <script src="./app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Crear `docs/app.js`**

```javascript
async function cargar() {
  const datos = await fetch('./data.json').then(r => r.json());
  document.getElementById('generado').textContent = datos.generado;

  // Métricas
  const m = datos.metricas;
  const cont = document.getElementById('metricas');
  const tarjetas = [
    { etiqueta: 'Aciertos', valor: m.aciertos_pct == null ? '—' : m.aciertos_pct + '%' },
    { etiqueta: 'Error medio (MAE)', valor: m.mae == null ? '—' : m.mae + ' °C' },
    { etiqueta: 'Días evaluados', valor: m.n },
  ];
  cont.innerHTML = tarjetas.map(t =>
    `<div class="card"><div class="valor">${t.valor}</div><div class="etiqueta">${t.etiqueta}</div></div>`
  ).join('');

  // Gráfica: histórico (últimos 60) + predicciones futuras
  const hist = datos.historico.slice(-60);
  const labelsHist = hist.map(d => d.fecha);
  const labelsPred = datos.predicciones.map(d => d.fecha_objetivo);
  const labels = labelsHist.concat(labelsPred);

  const serieReal = hist.map(d => d.temp_max_c).concat(labelsPred.map(() => null));
  const seriePred = labelsHist.map(() => null).concat(datos.predicciones.map(d => d.temp_max_pred_c));

  new Chart(document.getElementById('grafica'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Observado', data: serieReal, borderColor: '#0969da', tension: .3, spanGaps: false },
        { label: 'Predicción', data: seriePred, borderColor: '#cf222e', borderDash: [6, 4], tension: .3 },
      ],
    },
    options: { scales: { y: { title: { display: true, text: '°C' } } } },
  });

  // Tabla de verificaciones
  const tbody = document.querySelector('#tabla tbody');
  tbody.innerHTML = datos.evaluaciones.slice().reverse().map(e => `
    <tr>
      <td>${e.fecha_objetivo}</td>
      <td>${e.pred_c} °C</td>
      <td>${e.real_c} °C</td>
      <td>${e.error_c > 0 ? '+' : ''}${e.error_c} °C</td>
      <td class="${e.acierto ? 'ok' : 'fail'}">${e.acierto ? '✅ Acierto' : '❌ Fallo'}</td>
    </tr>`).join('');
}
cargar();
```

- [ ] **Step 4: Verificación manual (smoke test local)**

Crear un `docs/data.json` de prueba y abrir la página:

```bash
python -c "import json,datetime; json.dump({'generado':datetime.datetime.now().isoformat(),'historico':[{'fecha':'2026-06-13','temp_max_c':33.0}],'predicciones':[{'fecha_objetivo':'2026-06-15','temp_max_pred_c':33.4}],'metricas':{'n':1,'mae':0.4,'aciertos_pct':100.0},'evaluaciones':[{'fecha_objetivo':'2026-06-13','pred_c':33.4,'real_c':33.0,'error_c':0.4,'acierto':True}]}, open('docs/data.json','w'))"
python -m http.server 8000 --directory docs
```

Abrir `http://localhost:8000` y confirmar: gráfica visible, 3 tarjetas de métricas, una fila en la tabla con ✅. Detener el servidor (Ctrl+C).

- [ ] **Step 5: Commit**

```bash
git add docs/index.html docs/app.js docs/.nojekyll docs/data.json
git commit -m "feat: dashboard estático con Chart.js"
```

---

## Task 14: Workflows de GitHub Actions

**Files:**
- Create: `.github/workflows/daily.yml`
- Create: `.github/workflows/backfill.yml`

- [ ] **Step 1: Crear `.github/workflows/daily.yml`**

```yaml
name: Pipeline diario

on:
  schedule:
    - cron: "0 12 * * *"   # 12:00 UTC = 07:00 Panamá
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  run:
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
      - name: Ejecutar pipeline
        env:
          WUNDERGROUND_API_KEY: ${{ secrets.WUNDERGROUND_API_KEY }}
        run: python -m src.pipeline
      - name: Commit de datos actualizados
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/ docs/data.json
          git commit -m "data: actualización diaria $(date -u +%Y-%m-%d)" || echo "Sin cambios"
          git push

  deploy-pages:
    needs: run
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

- [ ] **Step 2: Crear `.github/workflows/backfill.yml`**

```yaml
name: Backfill histórico

on:
  workflow_dispatch:
    inputs:
      desde:
        description: "Fecha inicio (YYYY-MM-DD)"
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
          PTF_DESDE: ${{ inputs.desde }}
        run: python -c "from datetime import date; from src import backfill; backfill.correr(date.fromisoformat('${{ inputs.desde }}'))"
      - name: Commit del histórico
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git commit -m "data: backfill desde ${{ inputs.desde }}" || echo "Sin cambios"
          git push
```

- [ ] **Step 3: Validar el YAML localmente**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily.yml')); yaml.safe_load(open('.github/workflows/backfill.yml')); print('YAML OK')"`
Expected: `YAML OK` (si falta PyYAML: `pip install pyyaml`)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "ci: workflows de pipeline diario y backfill"
```

---

## Task 15: README e instrucciones de puesta en marcha

**Files:**
- Create: `README.md`

- [ ] **Step 1: Crear `README.md`**

````markdown
# panama-temp-forecast 🌡️

Predicción auto-mejorable de la temperatura máxima diaria en Ciudad de Panamá
(estación **MPMG – Marcos A. Gelabert / Albrook**).

Cada día, un workflow de GitHub Actions: recolecta el máximo observado, evalúa
las predicciones pasadas (acierto/fallo), re-ajusta el modelo con corrección de
sesgo, predice los próximos 7 días y publica todo en un dashboard.

**Dashboard:** https://CesarG-09.github.io/panama-temp-forecast/

## Cómo funciona

`recolectar → evaluar → ajustar → predecir → exportar` (ver `src/pipeline.py`).
El modelo (`src/model.py`) es una climatología por día-del-año + anomalía
reciente + corrección de sesgo, detrás de una interfaz `ajustar/predecir`
intercambiable por algo más avanzado sin tocar el resto.

## Puesta en marcha

1. **Obtener la API key:** abre `https://www.wunderground.com/history/daily/pa/panama-city/MPMG`,
   abre las herramientas de desarrollo → pestaña *Network* → filtra `historical.json`,
   y copia el valor del parámetro `apiKey` de la petición.
2. **Guardar el secret:** repo → Settings → Secrets and variables → Actions →
   `New repository secret` → nombre `WUNDERGROUND_API_KEY`.
3. **Habilitar Pages:** Settings → Pages → Source: *GitHub Actions*.
4. **Cargar el histórico:** Actions → *Backfill histórico* → *Run workflow*
   (deja `2020-01-01`). Tarda según el rango.
5. **Listo:** el *Pipeline diario* corre solo cada día a las 12:00 UTC.

## Desarrollo local

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m pytest -v            # tests
export WUNDERGROUND_API_KEY=...  # (Windows: $env:WUNDERGROUND_API_KEY="...")
python -m src.pipeline         # corre el pipeline una vez
```

## Estructura

- `src/` — código del pipeline (scraper, model, evaluate, export, pipeline, backfill)
- `data/` — CSV versionados (observaciones, predicciones, evaluación)
- `docs/` — dashboard estático (GitHub Pages)
- `.github/workflows/` — automatización (diario + backfill)
- `docs/superpowers/` — spec de diseño y este plan
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README con puesta en marcha"
```

- [ ] **Step 3: Push de todo**

```bash
git push
```

---

## Notas de cierre

- **Verificación final:** `python -m pytest -v` debe quedar 100% verde antes del push final.
- **Datos vacíos al inicio:** hasta correr el backfill, `data/` no existe; el primer
  `pipeline` lo creará. El dashboard mostrará "—" en métricas hasta tener evaluaciones.
- **Mejora futura del modelo:** sustituir `Predictor` por un estimador de
  scikit-learn respetando la interfaz `ajustar(hist, evaluacion)` / `predecir(fechas)`
  y subir `MODELO_VERSION` en `config.py`.
