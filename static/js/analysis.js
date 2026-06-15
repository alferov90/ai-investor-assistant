function initAnalysisPage() {
  renderNav("/analysis");
  if (!getToken()) {
    const errorEl = document.getElementById("error");
    errorEl.textContent = "Войдите в аккаунт, чтобы запускать AI-анализ.";
    errorEl.classList.remove("hidden");
    document.getElementById("login-hint").classList.remove("hidden");
    return;
  }

  document.querySelectorAll(".chart-range-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".chart-range-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (currentTicker) loadPriceChart(currentTicker, btn.dataset.range);
    });
  });

  const params = new URLSearchParams(window.location.search);
  const initialTicker = params.get("ticker");
  if (initialTicker) {
    document.getElementById("ticker").value = initialTicker;
    analyze(initialTicker);
  }

  document.getElementById("search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const ticker = document.getElementById("ticker").value.trim().toUpperCase();
    if (ticker) analyze(ticker);
  });
}

let currentTicker = null;

document.addEventListener("DOMContentLoaded", initAnalysisPage);

function renderList(id, items) {
  const el = document.getElementById(id);
  if (!items.length) {
    el.innerHTML = `<li class="text-slate-500">Нет данных</li>`;
    return;
  }
  el.innerHTML = items
    .map((item) => `<li class="flex gap-2"><span class="text-slate-500">•</span>${item}</li>`)
    .join("");
}

function ratingColor(rating) {
  if (rating >= 8) return "text-emerald-400";
  if (rating >= 5) return "text-amber-400";
  return "text-red-400";
}

function renderStockMeta(stock) {
  document.getElementById("stock-name").textContent = stock.name;
  document.getElementById("stock-ticker").textContent = stock.ticker;
  document.getElementById("stock-price").textContent = formatMoney(
    stock.current_price,
    stock.currency
  );

  const meta = [
    ["P/E", stock.pe_ratio?.toFixed(2) ?? "—"],
    ["EPS", stock.eps?.toFixed(2) ?? "—"],
    ["Market Cap", stock.market_cap ? formatCompact(stock.market_cap) : "—"],
    ["Rev. Growth", stock.revenue_growth != null ? formatGrowth(stock.revenue_growth) : "—"],
  ];
  document.getElementById("stock-meta").innerHTML = meta
    .map(
      ([label, value]) => `
      <div class="bg-slate-950 rounded-lg p-3">
        <p class="text-slate-500 text-xs">${label}</p>
        <p class="font-medium mt-0.5">${value}</p>
      </div>
    `
    )
    .join("");
}

function renderAnalysis(analysis) {
  const ratingEl = document.getElementById("rating");
  ratingEl.textContent = analysis.rating;
  ratingEl.className = `font-display text-2xl font-bold ${ratingColor(analysis.rating)}`;

  createRatingGauge(document.getElementById("rating-gauge"), analysis.rating);

  renderList("strengths", analysis.strengths);
  renderList("weaknesses", analysis.weaknesses);
  renderList("risks", analysis.risks);
  document.getElementById("investment-conclusion").textContent = analysis.investment_conclusion;

  const badge = document.getElementById("ai-badge");
  if (analysis.ai_powered) {
    badge.textContent = "GPT";
    badge.className = "text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full";
  } else {
    badge.textContent = "Базовый";
    badge.className = "text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full";
  }

  document.getElementById("analysis-section").classList.remove("hidden");
}

async function loadPriceChart(ticker, range) {
  const changeEl = document.getElementById("chart-change");
  try {
    const history = await apiFetch(
      `/api/stocks/${encodeURIComponent(ticker)}/history?range=${encodeURIComponent(range)}`,
      { timeoutMs: 30000 }
    );
    const sign = history.change_percent >= 0 ? "+" : "";
    changeEl.textContent = `${sign}${history.change_percent.toFixed(2)}% за период`;
    changeEl.className = `chart-change ${history.change_percent >= 0 ? "positive" : "negative"}`;
    createPriceLineChart(document.getElementById("price-chart"), history);
  } catch {
    changeEl.textContent = "График недоступен";
    changeEl.className = "chart-change";
    destroyChart("price");
  }
}

async function analyze(ticker) {
  if (!getToken()) {
    window.location.href =
      "/login?next=" + encodeURIComponent("/analysis?ticker=" + encodeURIComponent(ticker));
    return;
  }

  const errorEl = document.getElementById("error");
  const loadingEl = document.getElementById("loading");
  const resultEl = document.getElementById("result");
  const analysisSection = document.getElementById("analysis-section");
  const chartsSection = document.getElementById("charts-section");

  currentTicker = ticker;
  errorEl.classList.add("hidden");
  resultEl.classList.add("hidden");
  analysisSection.classList.add("hidden");
  chartsSection.classList.add("hidden");
  destroyChart("price");
  destroyChart("rating-gauge");
  loadingEl.classList.remove("hidden");
  loadingEl.textContent = "Загрузка данных акции...";

  try {
    const stock = await apiFetch(`/api/stocks/${encodeURIComponent(ticker)}`, { timeoutMs: 30000 });
    renderStockMeta(stock);
    resultEl.classList.remove("hidden");
    chartsSection.classList.remove("hidden");

    const activeRange =
      document.querySelector(".chart-range-tab.active")?.dataset.range || "3mo";
    loadPriceChart(ticker, activeRange);

    loadingEl.textContent = "AI-анализ (до 60 сек)...";
    const analysis = await apiFetch(`/api/stocks/${encodeURIComponent(ticker)}/analysis`, {
      timeoutMs: 90000,
    });
    renderAnalysis(analysis);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    loadingEl.classList.add("hidden");
  }
}

function formatCompact(value) {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(0)}`;
}

function formatGrowth(value) {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}
