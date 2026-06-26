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
