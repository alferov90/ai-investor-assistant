if (!requireAuth()) throw new Error("redirecting");
renderNav("/dashboard");

let benchmarkState = { benchmark: "SPY", range: "3mo" };
let hasPortfolio = false;

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

  document.getElementById("total-value").textContent = formatMoney(stats.total_value);
  document.getElementById("total-cost").textContent = formatMoney(stats.total_cost);

  const pnlEl = document.getElementById("total-pnl");
  pnlEl.textContent = `${formatMoney(stats.total_pnl)} (${formatPercent(stats.total_pnl_percent)})`;
  pnlEl.className = `stat-value ${pnlClass(stats.total_pnl)}`;

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
    createAllocationDoughnut(
      document.getElementById("allocation-chart"),
      chartHoldings
    );
    createPnlBarChart(document.getElementById("pnl-chart"), chartHoldings);
  } else {
    chartsRow.classList.add("hidden");
  }

  const container = document.getElementById("top-holdings");
  if (!stats.top_holdings.length) {
    container.innerHTML = `
      <p class="text-sm" style="color: var(--text-muted);">Портфель пуст. <a href="/portfolio" class="link-accent">Добавьте первый тикер</a></p>
    `;
    return;
  }

  container.innerHTML = stats.top_holdings
    .map(
      (h) => `
      <div class="flex items-center justify-between py-3 divider-row">
        <div>
          <p class="font-medium">${h.ticker}</p>
          <p class="text-slate-400 text-sm">${h.name}</p>
        </div>
        <div class="text-right">
          <p class="font-medium">${formatMoney(h.value)}</p>
          <p class="text-sm ${pnlClass(h.pnl)}">${formatMoney(h.pnl)} (${formatPercent(h.pnl_percent)})</p>
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
    <p class="text-red-400 text-sm">${err.message}</p>
  `;
});
updateTelegramUI();
window.addEventListener("focus", updateTelegramUI);

document.getElementById("btn-portfolio-ai").onclick = async () => {
  const el = document.getElementById("portfolio-ai-result");
  el.classList.remove("hidden");
  el.innerHTML = `<p class="text-slate-400">AI анализирует портфель...</p>`;
  try {
    const data = await apiFetch("/api/portfolio/ai-analysis", { method: "POST", timeoutMs: 90000 });
    el.innerHTML = `
      <div class="flex items-center gap-2 mb-3">
        <h2 class="font-semibold text-lg">AI-анализ портфеля</h2>
        <span class="text-xs px-2 py-0.5 rounded-full ${data.ai_powered ? "bg-emerald-500/20 text-emerald-400" : "bg-slate-700 text-slate-300"}">${data.ai_powered ? "GPT" : "Базовый"}</span>
        <span class="text-amber-400 ml-auto">Рейтинг ${data.rating}/10</span>
      </div>
      <p class="text-slate-300 mb-4">${data.summary}</p>
      <p class="text-emerald-400 font-medium mb-4">${data.recommendation}</p>
      <div class="grid md:grid-cols-3 gap-4 text-sm">
        <div><h3 class="text-emerald-400 mb-1">Сильные</h3><ul>${data.strengths.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
        <div><h3 class="text-amber-400 mb-1">Слабые</h3><ul>${data.weaknesses.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
        <div><h3 class="text-red-400 mb-1">Риски</h3><ul>${data.risks.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<p class="text-red-400">${err.message}</p>`;
  }
};
