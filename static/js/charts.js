/* global Chart */

const CHART_PALETTE = [
  "#2dd4bf",
  "#38bdf8",
  "#a78bfa",
  "#fbbf24",
  "#34d399",
  "#f472b6",
  "#fb923c",
  "#818cf8",
];

const _chartInstances = new Map();

function destroyChart(key) {
  const chart = _chartInstances.get(key);
  if (chart) {
    chart.destroy();
    _chartInstances.delete(key);
  }
}

function registerChart(key, chart) {
  destroyChart(key);
  _chartInstances.set(key, chart);
}

function ratingHex(rating) {
  if (rating >= 8) return "#34d399";
  if (rating >= 5) return "#fbbf24";
  return "#f87171";
}

function pnlHex(value) {
  return value >= 0 ? "#34d399" : "#f87171";
}

function baseChartOptions(extra = {}) {
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.borderColor = "rgba(148, 163, 184, 0.12)";
  Chart.defaults.font.family = '"DM Sans", system-ui, sans-serif';

  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        labels: {
          color: "#94a3b8",
          padding: 16,
          usePointStyle: true,
          pointStyle: "circle",
        },
      },
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        titleColor: "#f1f5f9",
        bodyColor: "#94a3b8",
        borderColor: "rgba(148, 163, 184, 0.2)",
        borderWidth: 1,
        padding: 12,
        cornerRadius: 10,
        displayColors: true,
      },
    },
    ...extra,
  };
}

function makeLineGradient(ctx, chartArea, positive = true) {
  const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  if (positive) {
    g.addColorStop(0, "rgba(45, 212, 191, 0.35)");
    g.addColorStop(1, "rgba(45, 212, 191, 0)");
  } else {
    g.addColorStop(0, "rgba(248, 113, 113, 0.35)");
    g.addColorStop(1, "rgba(248, 113, 113, 0)");
  }
  return g;
}

function formatChartDate(dateStr, range) {
  const d = new Date(dateStr + "T00:00:00");
  if (range === "1mo") {
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  }
  return d.toLocaleDateString("ru-RU", { month: "short", year: "2-digit" });
}

function createPriceLineChart(canvas, history, key = "price") {
  if (typeof Chart === "undefined") return null;
  if (!canvas || !history?.points?.length) return null;

  const ctx = canvas.getContext("2d");
  const labels = history.points.map((p) => formatChartDate(p.date, history.range));
  const data = history.points.map((p) => p.close);
  const positive = history.change_percent >= 0;
  const lineColor = positive ? "#2dd4bf" : "#f87171";

  const chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: history.ticker,
          data,
          borderColor: lineColor,
          backgroundColor: (c) => {
            const { chart: ch } = c;
            if (!ch.chartArea) return "rgba(45, 212, 191, 0.1)";
            return makeLineGradient(ch.ctx, ch.chartArea, positive);
          },
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: lineColor,
          borderWidth: 2.5,
        },
      ],
    },
    options: baseChartOptions({
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 6, maxRotation: 0 },
        },
        y: {
          grid: { color: "rgba(148, 163, 184, 0.08)" },
          ticks: {
            callback: (v) => "$" + Number(v).toFixed(2),
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => ` $${Number(item.raw).toFixed(2)}`,
          },
        },
      },
    }),
  });

  registerChart(key, chart);
  return chart;
}

function createRatingGauge(canvas, rating, key = "rating-gauge") {
  if (!canvas) return null;

  const color = ratingHex(rating);
  const chart = new Chart(canvas.getContext("2d"), {
    type: "doughnut",
    data: {
      datasets: [
        {
          data: [rating, 10 - rating],
          backgroundColor: [color, "rgba(148, 163, 184, 0.12)"],
          borderWidth: 0,
          circumference: 200,
          rotation: 260,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "78%",
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
    plugins: [
      {
        id: "ratingCenter",
        afterDraw(ch) {
          const { ctx, chartArea } = ch;
          const cx = (chartArea.left + chartArea.right) / 2;
          const cy = (chartArea.top + chartArea.bottom) / 2 + 8;
          ctx.save();
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = color;
          ctx.font = '700 28px "Syne", system-ui, sans-serif';
          ctx.fillText(String(rating), cx, cy - 4);
          ctx.fillStyle = "#94a3b8";
          ctx.font = '500 11px "DM Sans", system-ui, sans-serif';
          ctx.fillText("из 10", cx, cy + 18);
          ctx.restore();
        },
      },
    ],
  });

  registerChart(key, chart);
  return chart;
}

function createAllocationDoughnut(canvas, holdings, key = "allocation") {
  if (!canvas || !holdings?.length) return null;

  const labels = holdings.map((h) => h.ticker);
  const values = holdings.map((h) => h.value);
  const colors = holdings.map((_, i) => CHART_PALETTE[i % CHART_PALETTE.length]);

  const chart = new Chart(canvas.getContext("2d"), {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderColor: "rgba(6, 8, 15, 0.8)",
          borderWidth: 2,
          hoverOffset: 8,
        },
      ],
    },
    options: baseChartOptions({
      cutout: "62%",
      plugins: {
        legend: {
          position: "right",
          labels: { boxWidth: 10, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: (item) => {
              const total = values.reduce((a, b) => a + b, 0);
              const pct = total ? ((item.raw / total) * 100).toFixed(1) : 0;
              return ` ${item.label}: $${Number(item.raw).toFixed(2)} (${pct}%)`;
            },
          },
        },
      },
    }),
  });

  registerChart(key, chart);
  return chart;
}

function createPnlBarChart(canvas, holdings, key = "pnl-bars") {
  if (!canvas || !holdings?.length) return null;

  const sorted = [...holdings].sort((a, b) => b.pnl - a.pnl);
  const labels = sorted.map((h) => h.ticker);
  const values = sorted.map((h) => h.pnl);
  const colors = values.map(pnlHex);

  const chart = new Chart(canvas.getContext("2d"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "P/L",
          data: values,
          backgroundColor: colors.map((c) => c + "cc"),
          borderColor: colors,
          borderWidth: 1,
          borderRadius: 6,
          borderSkipped: false,
        },
      ],
    },
    options: baseChartOptions({
      indexAxis: "y",
      scales: {
        x: {
          grid: { color: "rgba(148, 163, 184, 0.08)" },
          ticks: {
            callback: (v) => "$" + Number(v).toFixed(0),
          },
        },
        y: {
          grid: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => {
              const h = sorted[item.dataIndex];
              return ` $${Number(item.raw).toFixed(2)} (${h.pnl_percent >= 0 ? "+" : ""}${h.pnl_percent}%)`;
            },
          },
        },
      },
    }),
  });

  registerChart(key, chart);
  return chart;
}

function createRatingTimeline(canvas, records, key = "rating-timeline") {
  if (!canvas || !records?.length) return null;

  const sorted = [...records].sort(
    (a, b) => new Date(a.created_at) - new Date(b.created_at)
  );

  const byTicker = {};
  sorted.forEach((r) => {
    if (!byTicker[r.ticker]) byTicker[r.ticker] = [];
    byTicker[r.ticker].push(r);
  });

  const tickers = Object.keys(byTicker).slice(0, 6);
  const allDates = [...new Set(sorted.map((r) => r.created_at.slice(0, 10)))].sort();

  const datasets = tickers.map((ticker, i) => {
    const map = {};
    byTicker[ticker].forEach((r) => {
      map[r.created_at.slice(0, 10)] = r.rating;
    });
    return {
      label: ticker,
      data: allDates.map((d) => map[d] ?? null),
      borderColor: CHART_PALETTE[i % CHART_PALETTE.length],
      backgroundColor: CHART_PALETTE[i % CHART_PALETTE.length] + "33",
      tension: 0.3,
      spanGaps: true,
      pointRadius: 4,
      pointHoverRadius: 6,
      borderWidth: 2,
    };
  });

  const chart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: allDates.map((d) =>
        new Date(d + "T00:00:00").toLocaleDateString("ru-RU", {
          day: "numeric",
          month: "short",
        })
      ),
      datasets,
    },
    options: baseChartOptions({
      scales: {
        x: { grid: { display: false } },
        y: {
          min: 0,
          max: 10,
          grid: { color: "rgba(148, 163, 184, 0.08)" },
          ticks: { stepSize: 2 },
        },
      },
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 10, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: (item) => ` ${item.dataset.label}: ${item.raw}/10`,
          },
        },
      },
    }),
  });

  registerChart(key, chart);
  return chart;
}

function createSparkline(canvas, values, changePercent, key) {
  if (typeof Chart === "undefined") return null;
  if (!canvas || !values?.length) return null;

  const first = values[0];
  const last = values[values.length - 1];
  const delta = changePercent ?? (first ? ((last - first) / first) * 100 : 0);
  const positive = delta >= 0;
  const lineColor = positive ? "#2dd4bf" : "#f87171";

  const chart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: values.map((_, i) => i),
      datasets: [
        {
          data: values,
          borderColor: lineColor,
          backgroundColor: (c) => {
            const { chart: ch } = c;
            if (!ch.chartArea) return lineColor + "22";
            return makeLineGradient(ch.ctx, ch.chartArea, positive);
          },
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 0,
          borderWidth: 1.5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { display: false },
        y: {
          display: false,
          min: Math.min(...values) * 0.998,
          max: Math.max(...values) * 1.002,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
    },
  });

  registerChart(key, chart);
  return chart;
}

async function loadSparklines(container, tickers, range = "1mo") {
  if (!container || !tickers?.length) return;

  const unique = [...new Set(tickers.map((t) => t.toUpperCase()))];
  await Promise.all(
    unique.map(async (ticker) => {
      const canvas = container.querySelector(`canvas[data-sparkline="${ticker}"]`);
      if (!canvas) return;
      try {
        const history = await apiFetch(
          `/api/stocks/${encodeURIComponent(ticker)}/history?range=${encodeURIComponent(range)}`,
          { timeoutMs: 20000 }
        );
        const values = history.points.map((p) => p.close);
        createSparkline(canvas, values, history.change_percent, `spark-${ticker}`);
      } catch {
        canvas.parentElement?.classList.add("sparkline-empty");
      }
    })
  );
}
