if (!requireAuth()) throw new Error("redirecting");
renderNav("/dividends");

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

function marketBadge(market) {
  if (market === "moex") {
    return `<span class="badge badge-live text-xs">MOEX</span>`;
  }
  return `<span class="badge text-xs">US</span>`;
}

async function loadDividends() {
  const data = await apiFetch("/api/portfolio/dividends", { timeoutMs: 60000 });

  document.getElementById("stat-annual-usd").textContent = formatMoney(
    data.total_annual_income_usd,
    "USD"
  );
  document.getElementById("stat-annual-rub").textContent = formatMoney(
    data.total_annual_income_rub,
    "RUB"
  );
  document.getElementById("stat-received").textContent = formatMoney(
    data.dividends_received,
    "USD"
  );
  document.getElementById("stat-fx").textContent = data.usd_rub_rate
    ? `${data.usd_rub_rate.toFixed(2)} ₽`
    : "—";
  document.getElementById("stat-upcoming").textContent = String(data.upcoming.length);

  const upcomingEl = document.getElementById("upcoming-list");
  if (!data.upcoming.length) {
    upcomingEl.innerHTML = `<p class="text-sm" style="color: var(--text-muted);">Нет предстоящих выплат по MOEX-позициям. Добавьте SBER, GAZP, LKOH и др.</p>`;
  } else {
    upcomingEl.innerHTML = data.upcoming
      .map(
        (e) => `
      <div class="flex items-center justify-between py-3 divider-row">
        <div>
          <p class="font-medium">${e.ticker} ${marketBadge(e.market)}</p>
          <p class="text-sm" style="color: var(--text-muted);">отсечка ${formatDate(e.ex_date)}${e.pay_date && e.pay_date !== e.ex_date ? ` · выплата ${formatDate(e.pay_date)}` : ""}</p>
        </div>
        <p class="font-medium">${formatMoney(e.amount, e.currency)}</p>
      </div>
    `
      )
      .join("");
  }

  const holdingsEl = document.getElementById("holdings-list");
  const withYield = data.holdings.filter((h) => h.market === "moex" || h.annual_income);
  if (!withYield.length) {
    holdingsEl.innerHTML = `<p class="text-sm" style="color: var(--text-muted);">Нет MOEX-позиций с данными о дивидендах.</p>`;
    return;
  }

  holdingsEl.innerHTML = withYield
    .map(
      (h) => `
    <div class="py-3 divider-row">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="font-medium">${h.ticker} ${marketBadge(h.market)}</p>
          <p class="text-sm" style="color: var(--text-muted);">${h.name} · ${h.shares} шт.</p>
        </div>
        <div class="text-right">
          <p class="font-medium">${h.dividend_yield != null ? `${h.dividend_yield.toFixed(2)}%` : "—"}</p>
          <p class="text-sm" style="color: var(--text-muted);">доходность</p>
        </div>
      </div>
      <div class="flex flex-wrap gap-4 mt-2 text-sm">
        <span>Цена: ${formatMoney(h.price, h.currency)}</span>
        <span>Годовой доход: ${h.annual_income != null ? formatMoney(h.annual_income, h.currency) : "—"}</span>
        ${
          h.next_dividend
            ? `<span>Ближайшая: ${formatDate(h.next_dividend.ex_date)} · ${formatMoney(h.next_dividend.amount, h.next_dividend.currency)}</span>`
            : ""
        }
      </div>
      ${
        h.recent_dividends?.length
          ? `<p class="text-xs mt-2" style="color: var(--text-muted);">Последние: ${h.recent_dividends
              .slice(0, 3)
              .map((d) => `${formatDate(d.ex_date)} ${formatMoney(d.amount, d.currency)}`)
              .join(" · ")}</p>`
          : ""
      }
    </div>
  `
    )
    .join("");
}

loadDividends().catch((err) => {
  document.getElementById("stat-annual-usd").textContent = "—";
  document.getElementById("holdings-list").innerHTML = `<p class="text-red-400 text-sm">${err.message}</p>`;
});
