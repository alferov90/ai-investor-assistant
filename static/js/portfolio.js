if (!requireAuth()) throw new Error("redirecting");
renderNav("/portfolio");

const modal = document.getElementById("modal");
const form = document.getElementById("holding-form");
const tickerInput = document.getElementById("ticker");
const container = document.getElementById("holdings-list");

function openModal(holding = null) {
  document.getElementById("modal-title").textContent = holding ? "Редактировать позицию" : "Добавить тикер";
  document.getElementById("holding-id").value = holding ? holding.id : "";
  tickerInput.value = holding ? holding.ticker : "";
  tickerInput.disabled = !!holding;
  document.getElementById("shares").value = holding ? holding.shares : "";
  document.getElementById("avg_price").value = holding ? holding.avg_price : "";
  document.getElementById("notes").value = holding ? holding.notes || "" : "";
  document.getElementById("form-error").classList.add("hidden");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function closeModal() {
  modal.classList.add("hidden");
  modal.classList.remove("flex");
  form.reset();
  tickerInput.disabled = false;
}

document.getElementById("btn-add").onclick = () => openModal();
document.getElementById("btn-cancel").onclick = closeModal;

async function loadHoldings() {
  const [holdings, stats] = await Promise.all([
    apiFetch("/api/portfolio"),
    apiFetch("/api/portfolio/dashboard").catch(() => ({ chart_holdings: [] })),
  ]);

  if (!holdings.length) {
    container.innerHTML = `<p class="text-slate-500 text-sm">Портфель пуст. Нажмите «Добавить тикер».</p>`;
    return;
  }

  const quoteMap = Object.fromEntries(
    (stats.chart_holdings || []).map((h) => [h.ticker, h])
  );

  container.innerHTML = holdings
    .map((h) => {
      const q = quoteMap[h.ticker];
      const quoteLine = q
        ? `<p class="text-sm mt-1">${formatMoney(q.price)} · ${formatMoney(q.value)} · <span class="${pnlClass(q.pnl)}">${formatMoney(q.pnl)} (${formatPercent(q.pnl_percent)})</span></p>`
        : "";

      return `
      <div class="glass-card glass-card-padded card-with-sparkline">
        <div class="card-body">
          <p class="font-display font-semibold text-lg">${h.ticker}</p>
          <p class="text-sm" style="color: var(--text-muted);">${h.shares} шт. × $${Number(h.avg_price).toFixed(2)}</p>
          ${quoteLine}
          ${h.notes ? `<p class="text-sm mt-1" style="color: var(--text-muted);">${h.notes}</p>` : ""}
        </div>
        <div class="sparkline-wrap">
          <canvas data-sparkline="${h.ticker}" aria-hidden="true"></canvas>
        </div>
        <div class="card-actions flex-wrap">
          <a href="/analysis?ticker=${h.ticker}" class="btn btn-ghost btn-sm">Анализ</a>
          <button data-edit='${JSON.stringify(h)}' class="btn btn-secondary btn-sm">Изменить</button>
          <button data-delete="${h.id}" class="btn btn-secondary btn-sm text-negative">Удалить</button>
        </div>
      </div>
    `;
    })
    .join("");

  container.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.onclick = () => openModal(JSON.parse(btn.dataset.edit));
  });

  container.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("Удалить позицию?")) return;
      await apiFetch(`/api/portfolio/${btn.dataset.delete}`, { method: "DELETE" });
      loadHoldings();
    };
  });

  loadSparklines(
    container,
    holdings.map((h) => h.ticker),
    "1mo"
  );
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("form-error");
  errorEl.classList.add("hidden");

  const id = document.getElementById("holding-id").value;
  const body = {
    ticker: tickerInput.value.trim().toUpperCase(),
    shares: parseFloat(document.getElementById("shares").value),
    avg_price: parseFloat(document.getElementById("avg_price").value),
    notes: document.getElementById("notes").value,
  };

  try {
    if (id) {
      await apiFetch(`/api/portfolio/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          shares: body.shares,
          avg_price: body.avg_price,
          notes: body.notes,
        }),
      });
    } else {
      await apiFetch("/api/portfolio", { method: "POST", body: JSON.stringify(body) });
    }
    closeModal();
    loadHoldings();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

loadHoldings().catch((err) => {
  console.error(err);
  container.innerHTML = `<p class="text-red-400 text-sm">${err.message}</p>`;
});
