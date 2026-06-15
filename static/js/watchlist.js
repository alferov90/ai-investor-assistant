if (!requireAuth()) throw new Error("redirecting");
renderNav("/watchlist");

const modal = document.getElementById("modal");
document.getElementById("btn-add").onclick = () => { modal.classList.remove("hidden"); modal.classList.add("flex"); };
document.getElementById("cancel").onclick = () => { modal.classList.add("hidden"); modal.classList.remove("flex"); };

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
  const el = document.getElementById("list");
  if (!items.length) {
    el.innerHTML = `<p class="text-slate-500 text-sm">Watchlist пуст. Добавьте тикер.</p>`;
    return;
  }
  el.innerHTML = items.map((i) => `
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 flex justify-between items-center gap-4">
      <div>
        <p class="font-semibold text-lg">${i.ticker}</p>
        ${i.notes ? `<p class="text-slate-400 text-sm">${i.notes}</p>` : ""}
        ${i.current_price != null ? `<p class="text-sm mt-1">${formatMoney(i.current_price)} <span class="${pnlClass(i.change_percent)}">${formatPercent(i.change_percent || 0)}</span></p>` : ""}
      </div>
      <div class="flex gap-2">
        <a href="/analysis?ticker=${i.ticker}" class="text-emerald-400 text-sm hover:underline">Анализ</a>
        <button data-id="${i.id}" class="delete-btn text-red-400 text-sm">Удалить</button>
      </div>
    </div>
  `).join("");
  el.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.onclick = async () => {
      await apiFetch(`/api/watchlist/${btn.dataset.id}`, { method: "DELETE" });
      load();
    };
  });
}
load().catch(console.error);
