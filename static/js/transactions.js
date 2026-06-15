if (!requireAuth()) throw new Error("redirecting");
renderNav("/transactions");

const modal = document.getElementById("modal");
const listEl = document.getElementById("txn-list");
const typeLabels = { buy: "Покупка", sell: "Продажа", dividend: "Дивиденд" };
const typeColors = {
  buy: "text-positive",
  sell: "text-negative",
  dividend: "text-accent-2",
};

function fmtDate(iso) {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function openModal() {
  document.getElementById("form-error").classList.add("hidden");
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  document.getElementById("traded-at").value = now.toISOString().slice(0, 16);
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function closeModal() {
  modal.classList.add("hidden");
  modal.classList.remove("flex");
  document.getElementById("txn-form").reset();
}

document.getElementById("btn-add").onclick = openModal;
document.getElementById("btn-cancel").onclick = closeModal;

document.getElementById("txn-type").onchange = () => {
  const isDiv = document.getElementById("txn-type").value === "dividend";
  document.getElementById("shares").disabled = isDiv;
  if (isDiv) document.getElementById("shares").value = "0";
};

async function loadSummary() {
  const s = await apiFetch("/api/transactions/summary");
  document.getElementById("stat-count").textContent = s.transaction_count;
  const rEl = document.getElementById("stat-realized");
  rEl.textContent = formatMoney(s.realized_pnl);
  rEl.className = `stat-value ${pnlClass(s.realized_pnl)}`;
  document.getElementById("stat-dividends").textContent = formatMoney(s.dividends_total);
  document.getElementById("stat-buys-sells").textContent = `${s.buy_count} / ${s.sell_count}`;
}

async function loadTransactions() {
  const items = await apiFetch("/api/transactions");
  if (!items.length) {
    listEl.innerHTML = `<p class="text-sm" style="color: var(--text-muted);">Сделок пока нет. Добавьте вручную или импортируйте CSV.</p>`;
    return;
  }

  listEl.innerHTML = items
    .map((t) => {
      const qty =
        t.txn_type === "dividend"
          ? formatMoney(Number(t.price))
          : `${Number(t.shares)} шт. × ${formatMoney(Number(t.price))}`;
      return `
    <div class="glass-card glass-card-padded flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-display font-semibold">${t.ticker}</span>
          <span class="text-xs px-2 py-0.5 rounded-full ${typeColors[t.txn_type] || ""}" style="background: rgba(148,163,184,0.1);">${typeLabels[t.txn_type] || t.txn_type}</span>
          ${t.source === "csv" ? '<span class="text-xs" style="color: var(--text-muted);">CSV</span>' : ""}
        </div>
        <p class="text-sm mt-1">${qty}${Number(t.fee) ? ` · комиссия ${formatMoney(Number(t.fee))}` : ""}</p>
        <p class="text-xs mt-1" style="color: var(--text-muted);">${fmtDate(t.traded_at)}${t.notes ? ` · ${t.notes}` : ""}</p>
      </div>
      <button data-id="${t.id}" class="delete-btn text-negative text-sm">Удалить</button>
    </div>
  `;
    })
    .join("");

  listEl.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("Удалить сделку и пересчитать портфель?")) return;
      await apiFetch(`/api/transactions/${btn.dataset.id}`, { method: "DELETE" });
      await refresh();
    };
  });
}

async function refresh() {
  await Promise.all([loadSummary(), loadTransactions()]);
}

document.getElementById("txn-form").onsubmit = async (e) => {
  e.preventDefault();
  const err = document.getElementById("form-error");
  err.classList.add("hidden");
  const txnType = document.getElementById("txn-type").value;
  const body = {
    ticker: document.getElementById("ticker").value.trim().toUpperCase(),
    txn_type: txnType,
    shares: parseFloat(document.getElementById("shares").value) || 0,
    price: parseFloat(document.getElementById("price").value),
    fee: parseFloat(document.getElementById("fee").value) || 0,
    traded_at: new Date(document.getElementById("traded-at").value).toISOString(),
    notes: document.getElementById("notes").value,
  };
  try {
    await apiFetch("/api/transactions", { method: "POST", body: JSON.stringify(body) });
    closeModal();
    await refresh();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
};

document.getElementById("btn-import").onclick = async () => {
  const fileInput = document.getElementById("csv-file");
  const resultEl = document.getElementById("import-result");
  if (!fileInput.files?.length) {
    resultEl.textContent = "Выберите CSV файл";
    resultEl.className = "text-sm mt-3 text-negative";
    resultEl.classList.remove("hidden");
    return;
  }

  const form = new FormData();
  form.append("file", fileInput.files[0]);
  resultEl.textContent = "Импорт...";
  resultEl.className = "text-sm mt-3";
  resultEl.classList.remove("hidden");

  try {
    const token = getToken();
    const res = await fetch("/api/transactions/import", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Import failed");

    let msg = `Импортировано ${data.imported} сделок. Позиций в портфеле: ${data.holdings_updated}.`;
    if (data.realized_pnl) msg += ` Реализованный P/L: ${formatMoney(data.realized_pnl)}.`;
    if (data.errors?.length) msg += ` Пропущено: ${data.errors.length}.`;
    resultEl.textContent = msg;
    resultEl.className = "text-sm mt-3 text-positive";
    fileInput.value = "";
    await refresh();
  } catch (ex) {
    resultEl.textContent = ex.message;
    resultEl.className = "text-sm mt-3 text-negative";
  }
};

refresh().catch((err) => {
  listEl.innerHTML = `<p class="text-red-400 text-sm">${err.message}</p>`;
});
