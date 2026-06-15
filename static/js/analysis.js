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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function splitConclusion(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+(?=[А-ЯA-ZЁ])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseVerdict(sentence) {
  const match = sentence.match(/Вердикт:\s*([^;.!?]+)(?:;\s*уверенность\s*([^.!?]+))?/i);
  if (!match) return null;
  return {
    verdict: match[1].trim().toUpperCase(),
    confidence: (match[2] || "").trim().replace(/\.$/, ""),
  };
}

function formatNewsDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Дата не указана";
  return date.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function normalizeUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function renderConclusion(text) {
  const el = document.getElementById("investment-conclusion");
  const parts = splitConclusion(text);
  const verdict = parts.length ? parseVerdict(parts[0]) : null;
  const body = verdict ? parts.slice(1) : parts;

  if (!parts.length) {
    el.innerHTML = `<p class="conclusion-muted">Вывод пока недоступен.</p>`;
    return;
  }

  const labels = ["Контекст", "Главный риск", "Триггеры"];
  el.innerHTML = `
    ${
      verdict
        ? `<div class="conclusion-verdict">
            <div>
              <p class="conclusion-label">Вердикт</p>
              <p class="conclusion-title">${escapeHtml(verdict.verdict)}</p>
            </div>
            ${
              verdict.confidence
                ? `<span class="conclusion-confidence">Уверенность: ${escapeHtml(verdict.confidence)}</span>`
                : ""
            }
          </div>`
        : ""
    }
    <div class="conclusion-points">
      ${body
        .map(
          (sentence, index) => `
          <div class="conclusion-point">
            <span class="conclusion-point-label">${labels[index] || "Деталь"}</span>
            <p>${escapeHtml(sentence)}</p>
          </div>
        `
        )
        .join("")}
    </div>
  `;
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

  renderContext(analysis);

  renderList("strengths", analysis.strengths);
  renderList("weaknesses", analysis.weaknesses);
  renderList("risks", analysis.risks);
  renderConclusion(analysis.investment_conclusion);

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

function renderContext(analysis) {
  const section = document.getElementById("context-section");
  section.classList.remove("hidden");

  const banner = document.getElementById("earnings-banner");
  const earningsText = document.getElementById("earnings-text");
  if (analysis.upcoming_earnings) {
    const ue = analysis.upcoming_earnings;
    banner.classList.remove("hidden");
    let text = `Дата: ${ue.date}`;
    if (ue.eps_estimate != null) text += ` · EPS consensus: $${ue.eps_estimate.toFixed(2)}`;
    if (analysis.previous_rating != null) {
      text += ` · Прошлый AI-рейтинг: ${analysis.previous_rating}/10`;
    }
    earningsText.textContent = text;
  } else {
    banner.classList.add("hidden");
  }

  const newsSection = document.getElementById("news-section");
  const newsList = document.getElementById("news-list");
  if (analysis.news?.length) {
    newsSection.classList.remove("hidden");
    newsList.innerHTML = analysis.news
      .map((n, index) => {
        const headline = n.headline_ru || n.headline || `Новость ${index + 1}`;
        const summary = String(n.summary_ru || n.summary || "").trim();
        const url = normalizeUrl(n.url);
        const source = n.source || "Источник";
        const summaryPreview = summary.length > 210 ? `${summary.slice(0, 210)}…` : summary;
        return `
          <article class="news-card">
            <div class="news-card-topline">
              <span class="news-source">${escapeHtml(source)}</span>
              <span class="news-date">${formatNewsDate(n.published_at)}</span>
            </div>
            <h4 class="news-title">${escapeHtml(headline)}</h4>
            ${
              summaryPreview
                ? `<p class="news-summary">${escapeHtml(summaryPreview)}</p>`
                : `<p class="news-summary news-summary-muted">Краткое описание недоступно, откройте источник для деталей.</p>`
            }
            ${
              url
                ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="news-link">
                    <span>Читать источник</span>
                    <span aria-hidden="true">→</span>
                  </a>`
                : ""
            }
          </article>
        `;
      })
      .join("");
  } else {
    newsSection.classList.add("hidden");
  }

  const histSection = document.getElementById("earnings-history");
  const histList = document.getElementById("earnings-list");
  if (analysis.earnings?.length) {
    histSection.classList.remove("hidden");
    histList.innerHTML = analysis.earnings
      .map((e) => {
        const parts = [e.date];
        if (e.period) parts.push(e.period);
        if (e.eps_actual != null) parts.push(`EPS ${e.eps_actual}`);
        if (e.eps_estimate != null) parts.push(`est ${e.eps_estimate}`);
        if (e.surprise_pct != null) parts.push(`${e.surprise_pct >= 0 ? "+" : ""}${e.surprise_pct.toFixed(1)}%`);
        return `<p>${parts.join(" · ")}</p>`;
      })
      .join("");
  } else {
    histSection.classList.add("hidden");
  }
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
  const contextSection = document.getElementById("context-section");

  currentTicker = ticker;
  errorEl.classList.add("hidden");
  resultEl.classList.add("hidden");
  analysisSection.classList.add("hidden");
  chartsSection.classList.add("hidden");
  contextSection.classList.add("hidden");
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
