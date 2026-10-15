const PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea", "#0891b2"];

function showChartMessage(canvas, empty, message) {
  canvas.style.display = "none";
  empty.textContent = message;
  empty.style.display = "block";

  const legend = document.getElementById("chart-legend");
  if (legend) {
    legend.remove();
  }
}

function ensureLegend(canvas, series) {
  let legend = document.getElementById("chart-legend");
  if (!legend) {
    legend = document.createElement("div");
    legend.id = "chart-legend";
    canvas.insertAdjacentElement("afterend", legend);
  }

  legend.style.display = "flex";
  legend.style.flexWrap = "wrap";
  legend.style.gap = "0.75rem";
  legend.style.margin = "0.75rem 0 0";
  legend.innerHTML = "";

  for (const item of series) {
    const entry = document.createElement("span");
    entry.style.display = "inline-flex";
    entry.style.alignItems = "center";
    entry.style.gap = "0.35rem";
    entry.style.fontSize = "0.9rem";

    const swatch = document.createElement("span");
    swatch.style.width = "0.75rem";
    swatch.style.height = "0.75rem";
    swatch.style.borderRadius = "999px";
    swatch.style.backgroundColor = item.color;

    const label = document.createElement("span");
    label.textContent = item.label;

    entry.appendChild(swatch);
    entry.appendChild(label);
    legend.appendChild(entry);
  }
}

function pickChartColors() {
  const darkMode = window.matchMedia("(prefers-color-scheme: dark)").matches;
  return {
    axis: darkMode ? "rgba(255, 255, 255, 0.85)" : "rgba(17, 24, 39, 0.9)",
    grid: darkMode ? "rgba(255, 255, 255, 0.18)" : "rgba(17, 24, 39, 0.12)",
    pointStroke: darkMode ? "#111827" : "#ffffff",
  };
}

function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(Math.round(rect.width || canvas.parentElement?.clientWidth || 640), 320);
  const height = Math.max(Number(canvas.getAttribute("height")) || 120, 120);

  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  canvas.width = width * dpr;
  canvas.height = height * dpr;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.scale(dpr, dpr);
  return { ctx, width, height };
}

function computeBounds(series) {
  const xValues = [];
  const yValues = [];

  for (const item of series) {
    for (const point of item.points) {
      xValues.push(point.x);
      yValues.push(point.y);
    }
  }

  let minX = Math.min(...xValues);
  let maxX = Math.max(...xValues);
  if (minX === maxX) {
    minX -= 60 * 60 * 1000;
    maxX += 60 * 60 * 1000;
  }

  let minY = Math.min(...yValues);
  let maxY = Math.max(...yValues);
  if (minY === maxY) {
    const padding = Math.abs(minY) > 1 ? Math.abs(minY) * 0.1 : 1;
    minY -= padding;
    maxY += padding;
  } else {
    const padding = (maxY - minY) * 0.08;
    minY -= padding;
    maxY += padding;
  }

  return { minX, maxX, minY, maxY };
}

function formatTickLabel(timestamp, span) {
  const options =
    span > 12 * 60 * 60 * 1000
      ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
      : { hour: "2-digit", minute: "2-digit" };
  return new Intl.DateTimeFormat(undefined, options).format(new Date(timestamp));
}

function formatValue(value, range) {
  const maximumFractionDigits = range < 1 ? 3 : range < 10 ? 2 : 1;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);
}

function drawAxes(ctx, width, height, bounds, colors) {
  const margin = { top: 16, right: 12, bottom: 28, left: 52 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const spanX = bounds.maxX - bounds.minX;
  const spanY = bounds.maxY - bounds.minY;

  const toCanvasX = (value) => margin.left + ((value - bounds.minX) / spanX) * chartWidth;
  const toCanvasY = (value) => margin.top + (1 - (value - bounds.minY) / spanY) * chartHeight;

  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 1;
  ctx.font = "12px sans-serif";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = colors.grid;
  ctx.fillStyle = colors.axis;

  const yTicks = 5;
  for (let i = 0; i <= yTicks; i += 1) {
    const ratio = i / yTicks;
    const y = margin.top + ratio * chartHeight;
    const value = bounds.maxY - ratio * spanY;

    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(width - margin.right, y);
    ctx.stroke();

    ctx.textAlign = "right";
    ctx.fillText(formatValue(value, spanY), margin.left - 8, y);
  }

  const xTicks = 4;
  ctx.textBaseline = "top";
  for (let i = 0; i <= xTicks; i += 1) {
    const ratio = i / xTicks;
    const x = margin.left + ratio * chartWidth;
    const value = bounds.minX + ratio * spanX;

    ctx.beginPath();
    ctx.moveTo(x, margin.top);
    ctx.lineTo(x, height - margin.bottom);
    ctx.stroke();

    ctx.textAlign = i === 0 ? "left" : i === xTicks ? "right" : "center";
    ctx.fillText(formatTickLabel(value, spanX), x, height - margin.bottom + 8);
  }

  ctx.strokeStyle = colors.axis;
  ctx.beginPath();
  ctx.moveTo(margin.left, margin.top);
  ctx.lineTo(margin.left, height - margin.bottom);
  ctx.lineTo(width - margin.right, height - margin.bottom);
  ctx.stroke();

  return { toCanvasX, toCanvasY };
}

function drawSeries(ctx, series, project, colors) {
  for (const item of series) {
    if (item.points.length === 0) {
      continue;
    }

    ctx.strokeStyle = item.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    item.points.forEach((point, index) => {
      const x = project.toCanvasX(point.x);
      const y = project.toCanvasY(point.y);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    ctx.fillStyle = item.color;
    for (const point of item.points) {
      const x = project.toCanvasX(point.x);
      const y = project.toCanvasY(point.y);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = colors.pointStroke;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }
}

function renderChart(canvas, series) {
  const colors = pickChartColors();
  const { ctx, width, height } = setupCanvas(canvas);
  const bounds = computeBounds(series);
  const project = drawAxes(ctx, width, height, bounds, colors);
  drawSeries(ctx, series, project, colors);
  ensureLegend(canvas, series);
}

(async () => {
  const canvas = document.getElementById("chart");
  if (!canvas) return;

  const empty = document.getElementById("chart-empty");
  const sensorId = canvas.dataset.sensorId;
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  const res = await fetch(`/measurements?sensor_id=${sensorId}&since=${encodeURIComponent(since)}&limit=2000`);
  if (!res.ok) {
    showChartMessage(canvas, empty, `Failed to load measurements: ${res.status}`);
    return;
  }

  const rows = await res.json();
  if (rows.length === 0) {
    showChartMessage(canvas, empty, "No measurements in the last 24 hours.");
    return;
  }

  const byMetric = new Map();
  for (const measurement of rows) {
    const x = Date.parse(measurement.recorded_at);
    const y = Number(measurement.value);
    if (Number.isNaN(x) || Number.isNaN(y)) {
      continue;
    }

    if (!byMetric.has(measurement.metric)) {
      byMetric.set(measurement.metric, []);
    }
    byMetric.get(measurement.metric).push({ x, y, unit: measurement.unit });
  }

  const series = [];
  let index = 0;
  for (const [metric, points] of byMetric.entries()) {
    points.sort((left, right) => left.x - right.x);
    const unit = points[0]?.unit ?? "";
    series.push({
      label: unit ? `${metric} (${unit})` : metric,
      color: PALETTE[index % PALETTE.length],
      points,
    });
    index += 1;
  }

  if (series.length === 0) {
    showChartMessage(canvas, empty, "No plottable measurements in the last 24 hours.");
    return;
  }

  empty.style.display = "none";
  canvas.style.display = "block";
  renderChart(canvas, series);
  window.addEventListener("resize", () => renderChart(canvas, series));
})();
