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
