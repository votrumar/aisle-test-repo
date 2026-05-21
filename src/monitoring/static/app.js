(async () => {
  const canvas = document.getElementById("chart");
  if (!canvas) return;
  const sensorId = canvas.dataset.sensorId;
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  const res = await fetch(`/measurements?sensor_id=${sensorId}&since=${encodeURIComponent(since)}&limit=2000`);
  if (!res.ok) {
    document.getElementById("chart-empty").textContent = `Failed to load measurements: ${res.status}`;
    document.getElementById("chart-empty").style.display = "block";
    return;
  }
  const rows = await res.json();
  if (rows.length === 0) {
    canvas.style.display = "none";
    document.getElementById("chart-empty").style.display = "block";
    return;
  }

  const byMetric = new Map();
  for (const m of rows) {
    if (!byMetric.has(m.metric)) byMetric.set(m.metric, []);
    byMetric.get(m.metric).push({ x: m.recorded_at, y: m.value, unit: m.unit });
  }
  for (const points of byMetric.values()) {
    points.sort((a, b) => new Date(a.x) - new Date(b.x));
  }

  const palette = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea", "#0891b2"];
  let i = 0;
  const datasets = [];
  for (const [metric, points] of byMetric) {
    const unit = points[0]?.unit ?? "";
    datasets.push({
      label: unit ? `${metric} (${unit})` : metric,
      data: points,
      borderColor: palette[i % palette.length],
      backgroundColor: palette[i % palette.length],
      tension: 0.2,
      pointRadius: 2,
    });
    i++;
  }

  new Chart(canvas.getContext("2d"), {
    type: "line",
    data: { datasets },
    options: {
      parsing: false,
      scales: {
        x: { type: "time", time: { tooltipFormat: "yyyy-MM-dd HH:mm:ss" } },
        y: { beginAtZero: false },
      },
      plugins: { legend: { position: "top" } },
    },
  });
})();
