if (!requireAuth()) throw new Error("redirecting");

const modal = document.getElementById("modal");
const form = document.getElementById("holding-form");
const tickerInput = document.getElementById("ticker");

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
  const holdings = await apiFetch("/api/portfolio");
  const container = document.getElementById("holdings-list");

  if (!holdings.length) {
    container.innerHTML = `<p class="text-slate-500 text-sm">Портфель пуст. Нажмите «Добавить тикер».</p>`;
    return;
  }

  container.innerHTML = holdings
    .map(
      (h) => `
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <p class="font-semibold text-lg">${h.ticker}</p>
          <p class="text-slate-400 text-sm">${h.shares} шт. × $${Number(h.avg_price).toFixed(2)}</p>
          ${h.notes ? `<p class="text-slate-500 text-sm mt-1">${h.notes}</p>` : ""}
        </div>
        <div class="flex gap-2">
          <a href="/analysis?ticker=${h.ticker}" class="text-sm text-emerald-400 hover:underline px-3 py-1.5">Анализ</a>
          <button data-edit='${JSON.stringify(h)}' class="text-sm border border-slate-700 px-3 py-1.5 rounded-lg hover:border-slate-500">Изменить</button>
          <button data-delete="${h.id}" class="text-sm text-red-400 border border-red-900/50 px-3 py-1.5 rounded-lg hover:bg-red-950/30">Удалить</button>
        </div>
      </div>
    `
    )
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

loadHoldings().catch(console.error);
