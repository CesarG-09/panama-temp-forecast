const HMIN = 6, HMAX = 18;
const REFRESCO_DATOS_MS = 30 * 60 * 1000;   // re-lee data.json cada 30 min (pico + desempeño)
const charts = {};
let datosBackend = {};    // último data.json
let curvaEnVivo = null;   // última curva del fetch en vivo (si la hubo)
let liveActivo = false;   // ¿el fetch en vivo ya entregó la temperatura actual?

// Crea (o recrea) un chart en un canvas, destruyendo el anterior para evitar
// el error "Canvas is already in use" al refrescar.
function pintar(canvasId, config) {
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(document.getElementById(canvasId), config);
}

async function cargar() {
  await refrescarDatos();                       // primer render desde data.json
  if (window.Live) {
    window.Live.iniciarEnVivo((d) => {
      if (d.actual) { liveActivo = true; pintarAhora(d.actual, true); }
      if (d.curva && d.curva.length) { curvaEnVivo = d.curva; dibujarCurva(); }
    });
  }
  setInterval(refrescarDatos, REFRESCO_DATOS_MS);
}

// Re-lee data.json (pico, pasadas, evolución, precisión por hora) al cargar y
// cada 30 min, para que la pestaña abierta no quede congelada. La temperatura
// actual y la curva las gobierna la capa en vivo; aquí solo se usan de respaldo.
async function refrescarDatos() {
  // cache-busting para no leer un data.json viejo de la CDN de Pages
  const datos = await fetch('./data.json?v=' + Date.now()).then(r => r.json());
  datosBackend = datos;
  document.getElementById('hoy').textContent = datos.hoy || '';
  pintarGenerado(datos.generado);
  pintarPico(datos.pico_hoy);
  if (!liveActivo) pintarAhora(datos.temp_actual, false);   // respaldo si el vivo aún no entrega
  dibujarCurva();
  renderPasadas(datos.pasadas_vs_real || []);
  renderEvolucion(datos.evolucion_modelo || []);
  renderTablaHistorica(datos.tabla_historica || []);
  renderErrorPorHora(datos.error_por_hora || []);
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
  const prob = document.getElementById('pico-prob');
  const meta = document.getElementById('pico-meta');
  if (!p) {
    num.textContent = '—';
    banda.textContent = '';
    prob.textContent = '';
    meta.textContent = 'aún sin predicción para hoy';
    return;
  }
  num.textContent = Math.trunc(p.pico_pred) + '°C';
  banda.textContent = `banda ${Math.trunc(p.p10)}° – ${Math.trunc(p.p90)}°`;
  if (p.prob_acierto != null) {
    let t = `≈${p.prob_acierto}% probable que este sea el pico · histórico de ${p.prob_n} día${p.prob_n === 1 ? '' : 's'}`;
    if (p.prob_n < 5) t += ' (pocos datos aún)';
    prob.textContent = t;
  } else {
    prob.textContent = '';
  }
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
  num.textContent = Math.trunc(actual.temp_c) + '°C';
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

// Dibuja la curva de hoy: en vivo si la hay, si no el respaldo de data.json,
// con la banda del pico previsto (de data.json) superpuesta.
function dibujarCurva() {
  const curva = curvaEnVivo || datosBackend.curva_hoy || [];
  const p = datosBackend.pico_hoy;
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
  pintar('curva', {
    type: 'line',
    data: { labels, datasets },
    options: { scales: { y: { title: { display: true, text: '°C' } },
                         x: { title: { display: true, text: 'hora del día (Panamá)' } } } },
  });
}

function renderPasadas(arr) {
  const nota = document.getElementById('pasadas-nota');
  if (!arr.length) { nota.hidden = false; return; }
  nota.hidden = true;
  const labels = arr.map(r => r.fecha.slice(5));
  pintar('pasadas', {
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

  pintar('evo-error', {
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

  pintar('evo-acierto', {
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
  pintar('error', {
    type: 'bar',
    data: {
      labels: arr.map(r => r.hora_decision + ':00'),
      datasets: [{ label: 'Error medio abs (°C)', data: arr.map(r => r.error_medio_abs),
                   backgroundColor: '#57606a' }],
    },
    options: { scales: { y: { beginAtZero: true, title: { display: true, text: '°C' } } } },
  });
}

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

cargar();
