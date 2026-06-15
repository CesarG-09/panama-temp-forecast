async function cargar() {
  // cache-busting para no leer un data.json viejo de la CDN de Pages
  const datos = await fetch('./data.json?v=' + Date.now()).then(r => r.json());
  document.getElementById('generado').textContent = datos.generado;

  // Métricas
  const m = datos.metricas;
  const tarjetas = [
    { etiqueta: 'Aciertos', valor: m.aciertos_pct == null ? '—' : m.aciertos_pct + '%' },
    { etiqueta: 'Error medio (MAE)', valor: m.mae == null ? '—' : m.mae + ' °C' },
    { etiqueta: 'Días evaluados', valor: m.n },
  ];
  document.getElementById('metricas').innerHTML = tarjetas.map(t =>
    `<div class="card"><div class="valor">${t.valor}</div><div class="etiqueta">${t.etiqueta}</div></div>`
  ).join('');

  // Próximas predicciones (tarjetas)
  const fmtDia = f => new Date(f + 'T00:00:00').toLocaleDateString('es', { weekday: 'short' });
  document.getElementById('preds').innerHTML = datos.predicciones.map(p => `
    <div class="pred">
      <div class="dia">${fmtDia(p.fecha_objetivo)}</div>
      <div class="temp">${p.temp_max_pred_c}°</div>
      <div class="fecha">${p.fecha_objetivo.slice(5)}</div>
    </div>`).join('') || '<p>Sin predicciones disponibles.</p>';

  // Gráfica: histórico (últimos 30) + predicciones futuras, conectadas
  const hist = datos.historico.slice(-30);
  const labels = hist.map(d => d.fecha).concat(datos.predicciones.map(d => d.fecha_objetivo));

  const serieReal = hist.map(d => d.temp_max_c).concat(datos.predicciones.map(() => null));
  // La predicción arranca en el último día observado para que la línea quede unida
  const seriePred = hist.map((d, i) => i === hist.length - 1 ? d.temp_max_c : null)
                        .concat(datos.predicciones.map(d => d.temp_max_pred_c));

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
  if (!datos.evaluaciones.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:#888">Aún sin verificaciones: aparecerán cuando un día predicho se observe.</td></tr>';
  } else {
    tbody.innerHTML = datos.evaluaciones.slice().reverse().map(e => `
      <tr>
        <td>${e.fecha_objetivo}</td>
        <td>${e.pred_c} °C</td>
        <td>${e.real_c} °C</td>
        <td>${e.error_c > 0 ? '+' : ''}${e.error_c} °C</td>
        <td class="${e.acierto ? 'ok' : 'fail'}">${e.acierto ? '✅ Acierto' : '❌ Fallo'}</td>
      </tr>`).join('');
  }
}
cargar();
