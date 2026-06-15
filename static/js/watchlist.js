if (!requireAuth()) throw new Error("redirecting");
renderNav("/watchlist");

const modal = document.getElementById("modal");
const listEl = document.getElementById("list");

document.getElementById("btn-add").onclick = () => {
  modal.classList.remove("hidden");
  modal.classList.add("flex");
};
document.getElementById("cancel").onclick = () => {
  modal.classList.add("hidden");
  modal.classList.remove("flex");
};

document.getElementById("form").onsubmit = async (e) => {
  e.preventDefault();
  const err = document.getElementById("error");
  err.classList.add("hidden");
  try {
    await apiFetch("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({
        ticker: document.getElementById("ticker").value.trim().toUpperCase(),
        notes: document.getElementById("notes").value,
      }),
    });
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    document.getElementById("form").reset();
    load();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
};

async function load() {
  const items = await apiFetch("/api/watchlist");
  if (!items.length) {
    listEl.innerHTML = `<p class="text-slate-500 text-sm">Watchlist пуст. Добавьте тикер.</p>`;
    return;
  }

  listEl.innerHTML = items
    .map(
      (i) => `
    <div class="glass-card glass-card-padded card-with-sparkline">
      <div class="card-body">
        <p class="font-display font-semibold text-lg">${i.ticker}</p>
        ${i.notes ? `<p class="text-sm" style="color: var(--text-muted);">${i.notes}</p>` : ""}
        ${
          i.current_price != null
            ? `<p class="text-sm mt-1 font-medium">${formatMoney(i.current_price)} <span class="${pnlClass(i.change_percent)}">${formatPercent(i.change_percent || 0)}</span></p>`
            : `<p class="text-sm mt-1" style="color: var(--text-muted);">Загрузка цены...</p>`
        }
      </div>
      <div class="sparkline-wrap">
        <canvas data-sparkline="${i.ticker}" aria-hidden="true"></canvas>
      </div>
      <div class="card-actions">
        <a href="/analysis?ticker=${i.ticker}" class="link-accent text-sm">Анализ</a>
        <button data-id="${i.id}" class="delete-btn text-negative text-sm">Удалить</button>
      </div>
    </div>
  `
    )
    .join("");

  listEl.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.onclick = async () => {
      await apiFetch(`/api/watchlist/${btn.dataset.id}`, { method: "DELETE" });
      load();
    };
  });

  loadSparklines(listEl, items.map((i) => i.ticker), "1mo");
}

load().catch(console.error);
