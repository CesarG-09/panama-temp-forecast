async function cargar() {
  // cache-busting para no leer un data.json viejo de la CDN de Pages
  const datos = await fetch('./data.json?v=' + Date.now()).then(r => r.json());
  document.getElementById('hoy').textContent = datos.hoy;

  // Hero: el pico (máxima) estimado de hoy + banda. NO es la temperatura de
  // la hora actual: es el techo del día, que suele darse cerca del mediodía.
  const hero = document.getElementById('hero');
  if (datos.pico_hoy) {
    const p = datos.pico_hoy;
    hero.innerHTML = `
      <div class="rotulo">Pico máximo previsto para HOY</div>
      <div class="pico">${p.pico_pred.toFixed(1)}°C</div>
      <div class="banda">banda ${p.p10.toFixed(1)}° – ${p.p90.toFixed(1)}°</div>
      <div class="nota">La máxima del día suele ocurrir entre 12 y 2 pm · estimación calculada a las ${p.hora_decision}:00 hora Panamá y afinada cada hora</div>`;
  } else {
    hero.innerHTML = '<div class="nota">Aún no hay predicción para hoy. Aparecerá dentro de la franja diurna (6am–4pm).</div>';
  }

  // Convergencia: p50 + banda p10/p90 a lo largo de las horas de hoy.
  const c = datos.convergencia_hoy || [];
  new Chart(document.getElementById('convergencia'), {
    type: 'line',
    data: {
      labels: c.map(r => r.hora_decision + ':00'),
      datasets: [
        { label: 'p90', data: c.map(r => r.p90), borderColor: '#ffd7d5',
          backgroundColor: 'rgba(207,34,46,.08)', fill: '+1', pointRadius: 0, tension: .3 },
        { label: 'p10', data: c.map(r => r.p10), borderColor: '#ffd7d5',
          pointRadius: 0, tension: .3 },
        { label: 'Pico estimado (p50)', data: c.map(r => r.pico_pred),
          borderColor: '#cf222e', borderWidth: 2, tension: .3 },
      ],
    },
    options: { scales: { y: { title: { display: true, text: '°C' } } } },
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
