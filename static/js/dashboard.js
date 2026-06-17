if (!requireAuth()) throw new Error("redirecting");
renderNav("/dashboard");

let benchmarkState = { benchmark: "SPY", range: "3mo" };
let hasPortfolio = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setTelegramStatus(text, cls) {
  const el = document.getElementById("telegram-status");
  el.textContent = text;
  el.className = `badge ${cls}`;
}

async function updateTelegramUI() {
  const actions = document.getElementById("telegram-actions");
  const errorEl = document.getElementById("telegram-error");
  errorEl.textContent = "";

  let user, status;
  try {
    [user, status] = await Promise.all([
      apiFetch("/api/auth/me"),
      apiFetch("/api/telegram/status").catch(() => null),
    ]);
  } catch {
    setTelegramStatus("Ошибка", "");
    return;
  }

  if (!status?.configured) {
    setTelegramStatus("Не настроен", "");
    actions.classList.add("hidden");
    errorEl.textContent = "Добавьте TELEGRAM_BOT_TOKEN в .env на сервере.";
    return;
  }

  actions.classList.remove("hidden");
  const connected = user.telegram_connected;
  const telegramLink = document.getElementById("telegram-link");

  if (connected) {
    const bot = status.bot_username ? `@${status.bot_username}` : "Telegram";
    setTelegramStatus(`Подключено (${bot})`, "badge-live");
    telegramLink.textContent = "Открыть бота";
    telegramLink.href = `https://t.me/${status.bot_username}`;
    document.getElementById("btn-telegram-disconnect").classList.remove("hidden");
  } else {
    setTelegramStatus("Не подключено", "");
    telegramLink.textContent = "Подключить Telegram";
    document.getElementById("btn-telegram-disconnect").classList.add("hidden");
    try {
      const res = await apiFetch("/api/telegram/link", { method: "POST" });
      telegramLink.href = res.link;
    } catch (err) {
      telegramLink.href = "#";
      errorEl.textContent = err.message;
    }
  }

  document.getElementById("btn-telegram-disconnect").onclick = async () => {
    await apiFetch("/api/telegram/disconnect", { method: "DELETE" });
    updateTelegramUI();
  };
}

function renderMover(mover) {
  if (!mover) return { value: "—", sub: "Нет данных" };
  const sign = mover.change_percent >= 0 ? "+" : "";
  return {
    value: `${escapeHtml(mover.ticker)} ${sign}${mover.change_percent.toFixed(2)}%`,
    sub: `${formatMoney(mover.price, mover.currency)} · ${escapeHtml(mover.name)}`,
  };
}

function renderDailySummary(summary) {
  const section = document.getElementById("daily-summary");
  const grid = document.getElementById("daily-summary-grid");
  const insights = document.getElementById("daily-insights");
  if (!section || !grid || !insights) return;

  section.classList.remove("hidden");
  const best = renderMover(summary.best_mover);
  const worst = renderMover(summary.worst_mover);
  const nextDividend = summary.upcoming_dividends?.[0];

  grid.innerHTML = `
    <div class="daily-tile">
      <p class="daily-label">Стоимость</p>
      <p class="daily-value">${formatDualMoney(summary.total_value_usd, summary.total_value_rub, summary.usd_rub_rate)}</p>
      <p class="daily-sub">${formatMoney(summary.total_pnl_usd)} · ${formatPercent(summary.total_pnl_percent)}</p>
    </div>
    <div class="daily-tile">
      <p class="daily-label">Лидер дня</p>
      <p class="daily-value">${best.value}</p>
      <p class="daily-sub">${best.sub}</p>
    </div>
    <div class="daily-tile">
      <p class="daily-label">Аутсайдер</p>
      <p class="daily-value">${worst.value}</p>
      <p class="daily-sub">${worst.sub}</p>
    </div>
    <div class="daily-tile">
      <p class="daily-label">Контроль</p>
      <p class="daily-value">${summary.active_alerts_count} алертов</p>
      <p class="daily-sub">${summary.watchlist_count} в watchlist${nextDividend ? ` · ${escapeHtml(nextDividend.ticker)} див.` : ""}</p>
    </div>
  `;

  insights.innerHTML = (summary.insights || [])
    .map(
      (item) => `
      <div class="daily-insight ${escapeHtml(item.level || "info")}">
        <p class="daily-insight-title">${escapeHtml(item.title)}</p>
        <p class="daily-insight-msg">${escapeHtml(item.message)}</p>
      </div>
    `
    )
    .join("");
}

async function loadDailySummary() {
  try {
    const summary = await apiFetch("/api/portfolio/daily-summary", { timeoutMs: 60000 });
    renderDailySummary(summary);
  } catch (err) {
    const section = document.getElementById("daily-summary");
    if (section) {
      section.classList.remove("hidden");
      document.getElementById("daily-summary-grid").innerHTML = "";
      document.getElementById("daily-insights").innerHTML = `<p class="text-red-400 text-sm">${escapeHtml(err.message)}</p>`;
    }
  }
}

function riskBadgeClass(level) {
  return `risk-badge risk-${level === "high" ? "high" : level === "medium" ? "medium" : level === "low" ? "low" : "ok"}`;
}

function riskLevelLabel(level, score) {
  const labels = { ok: "Низкий", low: "Умеренный", medium: "Средний", high: "Высокий" };
  return `${labels[level] || level} · ${score}/100`;
}

function renderRisks(risks) {
  const badge = document.getElementById("risk-badge");
  badge.textContent = riskLevelLabel(risks.level, risks.score);
  badge.className = riskBadgeClass(risks.level);

  const alertsEl = document.getElementById("risk-alerts");
  alertsEl.innerHTML = risks.alerts
    .map(
      (a) => `
    <div class="risk-alert risk-alert-${a.level}">
      <p class="risk-alert-title">${a.title}</p>
      <p class="risk-alert-msg">${a.message}</p>
    </div>
  `
    )
    .join("");

  const sectorsBlock = document.getElementById("risk-sectors");
  const sectorsList = document.getElementById("risk-sectors-list");
  const knownSectors = (risks.sectors || []).filter((s) => s.sector !== "Неизвестно");

  if (knownSectors.length) {
    sectorsBlock.classList.remove("hidden");
    sectorsList.innerHTML = knownSectors
      .slice(0, 5)
      .map(
        (s) => `
      <div class="sector-bar-row">
        <span class="truncate" style="color: var(--text-muted);" title="${s.sector}">${s.sector}</span>
        <div class="sector-bar-track">
          <div class="sector-bar-fill" style="width: ${Math.min(s.weight_pct, 100)}%;"></div>
        </div>
        <span class="text-right font-medium">${s.weight_pct.toFixed(0)}%</span>
      </div>
    `
      )
      .join("");
  } else {
    sectorsBlock.classList.add("hidden");
  }
}

async function loadBenchmark() {
  if (!hasPortfolio) return;

  const summaryEl = document.getElementById("benchmark-summary");
  const alphaEl = document.getElementById("benchmark-alpha");
  summaryEl.textContent = "Загрузка...";
  alphaEl.textContent = "—";

  try {
    const data = await apiFetch(
      `/api/portfolio/benchmark?benchmark=${encodeURIComponent(benchmarkState.benchmark)}&range=${encodeURIComponent(benchmarkState.range)}`,
      { timeoutMs: 60000 }
    );

    const sign = (v) => (v >= 0 ? "+" : "");
    summaryEl.textContent = `Портфель ${sign(data.portfolio_return)}${data.portfolio_return.toFixed(1)}% · ${data.benchmark} ${sign(data.benchmark_return)}${data.benchmark_return.toFixed(1)}%`;

    const alphaSign = data.alpha >= 0 ? "+" : "";
    alphaEl.textContent = `Альфа ${alphaSign}${data.alpha.toFixed(2)}% · просадка ${data.max_drawdown_pct.toFixed(1)}%`;
    alphaEl.className = `chart-change ${data.alpha >= 0 ? "positive" : "negative"} mb-2`;

    createBenchmarkChart(document.getElementById("benchmark-chart"), data);
  } catch (err) {
    summaryEl.textContent = "Бенчмарк недоступен";
    alphaEl.textContent = err.message;
    alphaEl.className = "chart-change mb-2";
    destroyChart("benchmark");
  }
}

async function loadRisks() {
  if (!hasPortfolio) return;

  try {
    const risks = await apiFetch(
      `/api/portfolio/risks?range=${encodeURIComponent(benchmarkState.range)}`,
      { timeoutMs: 60000 }
    );
    renderRisks(risks);
  } catch (err) {
    document.getElementById("risk-alerts").innerHTML = `<p class="text-red-400 text-sm">${err.message}</p>`;
  }
}

function initBenchmarkControls() {
  document.querySelectorAll(".benchmark-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".benchmark-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      benchmarkState.benchmark = btn.dataset.benchmark;
      loadBenchmark();
    });
  });

  document.querySelectorAll(".benchmark-range").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".benchmark-range").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      benchmarkState.range = btn.dataset.range;
      loadBenchmark();
      loadRisks();
    });
  });
}

initBenchmarkControls();

async function loadDashboard() {
  const [user, stats] = await Promise.all([
    apiFetch("/api/auth/me"),
    apiFetch("/api/portfolio/dashboard"),
  ]);

  document.getElementById("welcome").textContent = `Привет, ${user.name}`;

  document.getElementById("total-value").textContent = formatDualMoney(
    stats.total_value,
    stats.total_value_rub,
    stats.usd_rub_rate
  );
  document.getElementById("total-cost").textContent = formatDualMoney(
    stats.total_cost,
    stats.total_cost_rub,
    stats.usd_rub_rate
  );

  const pnlEl = document.getElementById("total-pnl");
  pnlEl.textContent = `${formatMoney(stats.total_pnl)} (${formatPercent(stats.total_pnl_percent)})`;
  pnlEl.className = `stat-value ${pnlClass(stats.total_pnl)}`;

  if (stats.usd_rub_rate) {
    const fxHint = document.getElementById("fx-hint");
    if (fxHint) fxHint.textContent = `USD/RUB ${stats.usd_rub_rate.toFixed(2)} · MOEX + US в USD-эквиваленте`;
  }

  document.getElementById("holdings-count").textContent = stats.holdings_count;

  hasPortfolio = stats.holdings_count > 0;
  const analyticsRow = document.getElementById("analytics-row");

  if (hasPortfolio) {
    analyticsRow.classList.remove("hidden");
    loadBenchmark();
    loadRisks();
  } else {
    analyticsRow.classList.add("hidden");
  }

  const chartsRow = document.getElementById("charts-row");
  const chartHoldings = stats.chart_holdings?.length
    ? stats.chart_holdings
    : stats.top_holdings;

  if (chartHoldings.length) {
    chartsRow.classList.remove("hidden");
    const chartData = chartHoldings.map((h) => ({
      ...h,
      value: h.value_usd ?? h.value,
      pnl: h.pnl_usd ?? h.pnl,
    }));
    createAllocationDoughnut(
      document.getElementById("allocation-chart"),
      chartData
    );
    createPnlBarChart(document.getElementById("pnl-chart"), chartData);
  } else {
    chartsRow.classList.add("hidden");
  }

  const container = document.getElementById("top-holdings");
  if (!stats.top_holdings.length) {
    container.innerHTML = `
      <div class="empty-state">
        Портфель пока пуст. Добавьте первую позицию вручную или синхронизируйте брокерский счёт.
        <a href="/portfolio" class="link-accent">Открыть портфель</a>
      </div>
    `;
    return;
  }

  container.innerHTML = stats.top_holdings
    .map(
      (h) => `
      <div class="data-row">
        <div>
          <p class="data-row-title">${escapeHtml(h.ticker)}</p>
          <p class="data-row-sub">${escapeHtml(h.name)}</p>
        </div>
        <div>
          <p class="data-row-value">${formatMoney(h.value, h.currency || "USD")}</p>
          <p class="data-row-meta ${pnlClass(h.pnl)}">${formatMoney(h.pnl, h.currency || "USD")} (${formatPercent(h.pnl_percent)})</p>
        </div>
      </div>
    `
    )
    .join("");
}

loadDashboard().catch((err) => {
  console.error(err);
  document.getElementById("welcome").textContent = "Не удалось загрузить dashboard";
  document.getElementById("total-value").textContent = "—";
  document.getElementById("total-cost").textContent = "—";
  document.getElementById("total-pnl").textContent = "—";
  document.getElementById("holdings-count").textContent = "—";
  document.getElementById("top-holdings").innerHTML = `
    <div class="empty-state text-negative">${escapeHtml(err.message)}</div>
  `;
});
loadDailySummary();
updateTelegramUI();
window.addEventListener("focus", updateTelegramUI);

document.getElementById("btn-portfolio-ai").onclick = async () => {
  const el = document.getElementById("portfolio-ai-result");
  el.classList.remove("hidden");
  el.innerHTML = `<div class="empty-state">AI анализирует портфель и собирает короткий вывод...</div>`;
  try {
    const data = await apiFetch("/api/portfolio/ai-analysis", { method: "POST", timeoutMs: 90000 });
    el.innerHTML = `
      <div class="section-head">
        <div>
          <p class="section-kicker">${data.ai_powered ? "GPT-анализ" : "Базовый анализ"}</p>
          <h2 class="chart-title">AI-анализ портфеля</h2>
        </div>
        <span class="risk-badge risk-${data.rating >= 8 ? "ok" : data.rating >= 6 ? "low" : data.rating >= 4 ? "medium" : "high"}">Рейтинг ${data.rating}/10</span>
      </div>
      <p class="daily-insight-msg mb-4">${escapeHtml(data.summary)}</p>
      <div class="daily-insight ok mb-4">
        <p class="daily-insight-title">Рекомендация</p>
        <p class="daily-insight-msg">${escapeHtml(data.recommendation)}</p>
      </div>
      <div class="analysis-meta-grid">
        <div class="daily-insight ok"><p class="daily-insight-title">Сильные стороны</p><ul class="clean-list">${data.strengths.map(s=>`<li>${escapeHtml(s)}</li>`).join("")}</ul></div>
        <div class="daily-insight warning"><p class="daily-insight-title">Слабые места</p><ul class="clean-list">${data.weaknesses.map(s=>`<li>${escapeHtml(s)}</li>`).join("")}</ul></div>
        <div class="daily-insight"><p class="daily-insight-title">Риски</p><ul class="clean-list">${data.risks.map(s=>`<li>${escapeHtml(s)}</li>`).join("")}</ul></div>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<div class="empty-state text-negative">${escapeHtml(err.message)}</div>`;
  }
};
