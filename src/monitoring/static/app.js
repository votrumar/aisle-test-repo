const PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea", "#0891b2"];
const TIME_FORMATTER = new Intl.DateTimeFormat(undefined, {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function ensureLegend(canvas, datasets) {
  let legend = document.getElementById("chart-legend");
  if (!legend) {
    legend = document.createElement("div");
    legend.id = "chart-legend";
    legend.style.display = "flex";
    legend.style.flexWrap = "wrap";
    legend.style.gap = "0.75rem";
    legend.style.margin = "0.5rem 0 1rem";
    canvas.insertAdjacentElement("afterend", legend);
  }

  legend.replaceChildren();
  for (const dataset of datasets) {
    const item = document.createElement("span");
    item.style.display = "inline-flex";
    item.style.alignItems = "center";
    item.style.gap = "0.35rem";
    item.style.fontSize = "0.85rem";

    const swatch = document.createElement("span");
    swatch.style.width = "0.85rem";
    swatch.style.height = "0.85rem";
    swatch.style.borderRadius = "999px";
    swatch.style.backgroundColor = dataset.color;

    const label = document.createElement("span");
    label.textContent = dataset.label;

    item.append(swatch, label);
    legend.append(item);
  }
}

function drawText(ctx, text, x, y, align = "left") {
  ctx.textAlign = align;
  ctx.fillText(text, x, y);
}

function drawChart(canvas, datasets) {
  const allPoints = datasets.flatMap((dataset) => dataset.data);
  const xValues = allPoints.map((point) => point.x).filter(Number.isFinite);
  const yValues = allPoints.map((point) => point.y).filter(Number.isFinite);
  if (xValues.length === 0 || yValues.length === 0) {
    return false;
  }

  let minX = Math.min(...xValues);
  let maxX = Math.max(...xValues);
  if (minX === maxX) {
    maxX = minX + 1;
  }

  let minY = Math.min(...yValues);
  let maxY = Math.max(...yValues);
  if (minY === maxY) {
    minY -= 1;
    maxY += 1;
  } else {
    const padding = (maxY - minY) * 0.1;
    minY -= padding;
    maxY += padding;
  }

  const cssWidth = Math.max(canvas.clientWidth || canvas.parentElement?.clientWidth || 640, 320);
  const cssHeight = Number(canvas.getAttribute("height")) || 120;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const margin = { top: 10, right: 12, bottom: 24, left: 48 };
  const plotWidth = cssWidth - margin.left - margin.right;
  const plotHeight = cssHeight - margin.top - margin.bottom;

  ctx.font = '11px sans-serif';
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(107, 114, 128, 0.35)";
  ctx.fillStyle = "rgba(31, 41, 55, 0.9)";

  for (let step = 0; step <= 4; step += 1) {
    const ratio = step / 4;
    const y = margin.top + plotHeight * ratio;
    const value = maxY - (maxY - minY) * ratio;

    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(margin.left + plotWidth, y);
    ctx.stroke();

    drawText(ctx, value.toFixed(2), margin.left - 6, y + 4, "right");
  }

  ctx.strokeStyle = "rgba(55, 65, 81, 0.7)";
  ctx.beginPath();
  ctx.moveTo(margin.left, margin.top);
  ctx.lineTo(margin.left, margin.top + plotHeight);
  ctx.lineTo(margin.left + plotWidth, margin.top + plotHeight);
  ctx.stroke();

  drawText(ctx, TIME_FORMATTER.format(new Date(minX)), margin.left, cssHeight - 6);
  drawText(ctx, TIME_FORMATTER.format(new Date(maxX)), cssWidth - margin.right, cssHeight - 6, "right");

  const scaleX = (value) => margin.left + ((value - minX) / (maxX - minX)) * plotWidth;
  const scaleY = (value) => margin.top + ((maxY - value) / (maxY - minY)) * plotHeight;

  for (const dataset of datasets) {
    if (dataset.data.length === 0) {
      continue;
    }

    ctx.strokeStyle = dataset.color;
    ctx.fillStyle = dataset.color;
    ctx.lineWidth = 2;
    ctx.beginPath();

    dataset.data.forEach((point, index) => {
      const x = scaleX(point.x);
      const y = scaleY(point.y);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    for (const point of dataset.data) {
      const x = scaleX(point.x);
      const y = scaleY(point.y);
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  return true;
}

(async () => {
  const canvas = document.getElementById("chart");
  if (!canvas) return;

  const empty = document.getElementById("chart-empty");
  const sensorId = canvas.dataset.sensorId;
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();

  const showMessage = (message) => {
    if (message) {
      empty.textContent = message;
    }
    empty.style.display = "block";
  };

  let rows;
  try {
    const res = await fetch(`/measurements?sensor_id=${sensorId}&since=${encodeURIComponent(since)}&limit=2000`);
    if (!res.ok) {
      showMessage(`Failed to load measurements: ${res.status}`);
      return;
    }

    rows = await res.json();
  } catch {
    showMessage("Failed to load measurements.");
    return;
  }
  if (rows.length === 0) {
    canvas.style.display = "none";
    showMessage();
    return;
  }

  const byMetric = new Map();
  for (const measurement of rows) {
    const x = Date.parse(measurement.recorded_at);
    const y = Number(measurement.value);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      continue;
    }

    if (!byMetric.has(measurement.metric)) {
      byMetric.set(measurement.metric, []);
    }
    byMetric.get(measurement.metric).push({ x, y, unit: measurement.unit });
  }

  const datasets = [];
  let colorIndex = 0;
  for (const [metric, points] of byMetric) {
    points.sort((left, right) => left.x - right.x);
    const unit = points[0]?.unit ?? "";
    datasets.push({
      label: unit ? `${metric} (${unit})` : metric,
      color: PALETTE[colorIndex % PALETTE.length],
      data: points,
    });
    colorIndex += 1;
  }

  if (datasets.length === 0 || !drawChart(canvas, datasets)) {
    canvas.style.display = "none";
    showMessage("Measurements could not be plotted.");
    return;
  }

  canvas.style.display = "block";
  empty.style.display = "none";
  ensureLegend(canvas, datasets);
  window.addEventListener("resize", () => drawChart(canvas, datasets), { passive: true });
})();
