if (!requireAuth()) throw new Error("redirecting");
renderNav("/history");

function fmtDate(iso) {
  return new Date(iso).toLocaleString("ru-RU");
}

async function load(ticker) {
  const url = ticker ? `/api/analyses/history?ticker=${encodeURIComponent(ticker)}` : "/api/analyses/history";
  const items = await apiFetch(url);
  const el = document.getElementById("list");
  const chartSection = document.getElementById("rating-chart-section");

  if (!items.length) {
    el.innerHTML = `<p class="text-slate-500">История пуста. Запустите анализ на странице «Анализ».</p>`;
    chartSection.classList.add("hidden");
    destroyChart("rating-timeline");
    return;
  }

  if (items.length >= 2) {
    chartSection.classList.remove("hidden");
    createRatingTimeline(document.getElementById("rating-timeline"), items);
  } else {
    chartSection.classList.add("hidden");
    destroyChart("rating-timeline");
  }

  el.innerHTML = items.map((r) => `
    <div class="glass-card glass-card-padded flex justify-between items-center cursor-pointer record hover:border-teal-500/30" data-id="${r.id}">
      <div>
        <span class="font-display font-semibold">${r.ticker}</span> — ${r.name}
        <p class="text-sm mt-1" style="color: var(--text-muted);">${fmtDate(r.created_at)} · ${formatMoney(Number(r.current_price))} · рейтинг ${r.rating}/10 ${r.ai_powered ? "GPT" : "базовый"}</p>
      </div>
      <span class="link-accent text-sm">Подробнее →</span>
    </div>
  `).join("");
  el.querySelectorAll(".record").forEach((row) => {
    row.onclick = () => showDetail(row.dataset.id);
  });
}

async function showDetail(id) {
  const r = await apiFetch(`/api/analyses/history/${id}`);
  const el = document.getElementById("detail");
  el.classList.remove("hidden");
  el.innerHTML = `
    <h2 class="text-xl font-bold mb-2">${r.ticker} — ${r.name}</h2>
    <p class="text-slate-400 text-sm mb-4">${fmtDate(r.created_at)} · рейтинг ${r.rating}/10</p>
    <p class="mb-4">${r.investment_conclusion}</p>
    <div class="grid md:grid-cols-3 gap-4 text-sm">
      <div><h3 class="text-emerald-400 mb-2">Сильные</h3><ul>${r.strengths.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
      <div><h3 class="text-amber-400 mb-2">Слабые</h3><ul>${r.weaknesses.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
      <div><h3 class="text-red-400 mb-2">Риски</h3><ul>${r.risks.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
    </div>
  `;
  el.scrollIntoView({ behavior: "smooth" });
}

document.getElementById("btn-filter").onclick = () => {
  const t = document.getElementById("filter").value.trim().toUpperCase();
  load(t || undefined);
};

load().catch(console.error);
