if (!requireAuth()) throw new Error("redirecting");

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

function renderList(id, items) {
  document.getElementById(id).innerHTML = items
    .map((item) => `<li class="flex gap-2"><span class="text-slate-500">•</span>${item}</li>`)
    .join("");
}

async function analyze(ticker) {
  const errorEl = document.getElementById("error");
  const loadingEl = document.getElementById("loading");
  const resultEl = document.getElementById("result");

  errorEl.classList.add("hidden");
  resultEl.classList.add("hidden");
  loadingEl.classList.remove("hidden");

  try {
    const data = await apiFetch(`/api/stocks/${encodeURIComponent(ticker)}/analysis`);
    const q = data.quote;

    document.getElementById("stock-name").textContent = q.name;
    document.getElementById("stock-ticker").textContent = q.ticker;
    document.getElementById("stock-price").textContent = formatMoney(q.price, q.currency);
    const changeEl = document.getElementById("stock-change");
    changeEl.textContent = `${formatMoney(q.change, q.currency)} (${formatPercent(q.change_percent)})`;
    changeEl.className = `text-sm ${pnlClass(q.change)}`;

    const meta = [
      ["P/E", q.pe_ratio?.toFixed(2) ?? "—"],
      ["52w High", q.fifty_two_week_high ? formatMoney(q.fifty_two_week_high, q.currency) : "—"],
      ["52w Low", q.fifty_two_week_low ? formatMoney(q.fifty_two_week_low, q.currency) : "—"],
      ["Sector", q.sector ?? "—"],
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

    document.getElementById("summary").textContent = data.summary;
    renderList("strengths", data.strengths);
    renderList("risks", data.risks);
    document.getElementById("recommendation").textContent = data.recommendation;

    const badge = document.getElementById("ai-badge");
    if (data.ai_powered) badge.classList.remove("hidden");
    else badge.classList.add("hidden");

    resultEl.classList.remove("hidden");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    loadingEl.classList.add("hidden");
  }
}
