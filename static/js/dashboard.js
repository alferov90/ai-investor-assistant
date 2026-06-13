if (!requireAuth()) throw new Error("redirecting");

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
  pnlEl.className = `text-2xl font-bold mt-1 ${pnlClass(stats.total_pnl)}`;

  document.getElementById("holdings-count").textContent = stats.holdings_count;

  const container = document.getElementById("top-holdings");
  if (!stats.top_holdings.length) {
    container.innerHTML = `
      <p class="text-slate-500 text-sm">Портфель пуст. <a href="/portfolio" class="text-emerald-400 hover:underline">Добавьте первый тикер</a></p>
    `;
    return;
  }

  container.innerHTML = stats.top_holdings
    .map(
      (h) => `
      <div class="flex items-center justify-between py-3 border-b border-slate-800 last:border-0">
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
});
