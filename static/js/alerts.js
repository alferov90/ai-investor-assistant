if (!requireAuth()) throw new Error("redirecting");
renderNav("/alerts");

const LABELS = { above: "Цена >", below: "Цена <", change_up: "Рост ≥", change_down: "Падение ≥" };
const modal = document.getElementById("modal");
document.getElementById("btn-add").onclick = () => { modal.classList.remove("hidden"); modal.classList.add("flex"); };
document.getElementById("cancel").onclick = () => { modal.classList.add("hidden"); modal.classList.remove("flex"); };

document.getElementById("form").onsubmit = async (e) => {
  e.preventDefault();
  const err = document.getElementById("error");
  err.classList.add("hidden");
  try {
    await apiFetch("/api/alerts", {
      method: "POST",
      body: JSON.stringify({
        ticker: document.getElementById("ticker").value.trim().toUpperCase(),
        condition_type: document.getElementById("condition").value,
        target_value: parseFloat(document.getElementById("target").value),
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
  const items = await apiFetch("/api/alerts");
  const el = document.getElementById("list");
  if (!items.length) {
    el.innerHTML = `<p class="text-slate-500">Нет алертов.</p>`;
    return;
  }
  el.innerHTML = items.map((a) => `
    <div class="glass-card glass-card-padded flex justify-between items-center gap-4">
      <div>
        <span class="font-display font-semibold ${a.is_active ? "" : "opacity-50 line-through"}">${a.ticker}</span>
        <span class="text-sm ml-2" style="color: var(--text-muted);">${LABELS[a.condition_type]} ${a.target_value}${a.condition_type.startsWith("change") ? "%" : "$"}</span>
        ${a.last_triggered_at ? `<p class="text-xs mt-1" style="color: var(--text-muted);">Срабатывал: ${new Date(a.last_triggered_at).toLocaleString("ru-RU")}</p>` : ""}
      </div>
      <div class="flex gap-2">
        <button data-id="${a.id}" data-active="${!a.is_active}" class="toggle btn btn-ghost btn-sm">${a.is_active ? "Выкл" : "Вкл"}</button>
        <button data-id="${a.id}" class="del btn btn-secondary btn-sm text-negative">Удалить</button>
      </div>
    </div>
  `).join("");
  el.querySelectorAll(".del").forEach((b) => b.onclick = async () => { await apiFetch(`/api/alerts/${b.dataset.id}`, { method: "DELETE" }); load(); });
  el.querySelectorAll(".toggle").forEach((b) => b.onclick = async () => {
    await apiFetch(`/api/alerts/${b.dataset.id}/toggle?active=${b.dataset.active}`, { method: "PATCH" });
    load();
  });
}
load().catch(console.error);
