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
