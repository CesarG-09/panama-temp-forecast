async function cargar() {
  // cache-busting para no leer un data.json viejo de la CDN de Pages
  const datos = await fetch('./data.json?v=' + Date.now()).then(r => r.json());
  document.getElementById('hoy').textContent = datos.hoy;

  // Sello de "última actualización" en hora de Panamá (sea cual sea la zona del visor).
  if (datos.generado) {
    const fmt = new Date(datos.generado).toLocaleString('es-PA', {
      timeZone: 'America/Panama', day: '2-digit', month: 'short',
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
    document.getElementById('generado').textContent = fmt + ' (Panamá)';
  }

  // Hero: el pico (máxima) estimado de hoy + banda. NO es la temperatura de
  // la hora actual: es el techo del día, que suele darse cerca del mediodía.
  const hero = document.getElementById('hero');
  const p = datos.pico_hoy;
  if (p) {
    hero.innerHTML = `
      <div class="rotulo">Pico máximo previsto para HOY</div>
      <div class="pico">${p.pico_pred.toFixed(1)}°C</div>
      <div class="banda">banda ${p.p10.toFixed(1)}° – ${p.p90.toFixed(1)}°</div>
      <div class="nota">La máxima del día suele ocurrir entre 12 y 2 pm · estimación calculada a las ${p.hora_decision}:00 hora Panamá y afinada cada hora</div>`;
  } else {
    hero.innerHTML = '<div class="nota">Aún no hay predicción para hoy. Aparecerá dentro de la franja diurna (6am–4pm).</div>';
  }

  // Curva del día: la temperatura observada hoy subiendo, con la banda del
  // pico máximo previsto superpuesta (suele alcanzarse cerca del mediodía).
  const curva = datos.curva_hoy || [];
  const HMIN = 6, HMAX = 18;
  const labels = [];
  for (let h = HMIN; h <= HMAX; h++) labels.push(h + ':00');
  const porHora = {};
  curva.forEach(r => { porHora[r.hora] = r.temp_c; });
  const obs = labels.map((_, i) => ((HMIN + i) in porHora ? porHora[HMIN + i] : null));

  const datasets = [{
    label: 'Temperatura observada hoy', data: obs, borderColor: '#cf222e',
    backgroundColor: '#cf222e', borderWidth: 2, tension: .3, spanGaps: false, pointRadius: 2,
  }];
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
  new Chart(document.getElementById('curva'), {
    type: 'line',
    data: { labels, datasets },
    options: { scales: { y: { title: { display: true, text: '°C' } },
                         x: { title: { display: true, text: 'hora del día (Panamá)' } } } },
  });

  // Error por hora de decisión (barras).
  const e = datos.error_por_hora || [];
  new Chart(document.getElementById('error'), {
    type: 'bar',
    data: {
      labels: e.map(r => r.hora_decision + ':00'),
      datasets: [{ label: 'Error medio abs (°C)', data: e.map(r => r.error_medio_abs),
                   backgroundColor: '#0969da' }],
    },
    options: { scales: { y: { beginAtZero: true, title: { display: true, text: '°C' } } } },
  });

  // Picos reales recientes.
  const o = datos.observados_recientes || [];
  new Chart(document.getElementById('observados'), {
    type: 'line',
    data: {
      labels: o.map(r => r.fecha.slice(5)),
      datasets: [{ label: 'Pico real (°C)', data: o.map(r => r.temp_max_c),
                   borderColor: '#1a7f37', tension: .3, pointRadius: 2 }],
    },
    options: { scales: { y: { title: { display: true, text: '°C' } } } },
  });
}
cargar();
