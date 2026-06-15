if (!requireAuth()) throw new Error("redirecting");
renderNav("/dashboard");

function setTelegramStatus(text, cls) {
  const el = document.getElementById("telegram-status");
  el.textContent = text;
  el.className = `text-xs px-2 py-1 rounded-full ${cls}`;
}

async function updateTelegramUI() {
  const actions = document.getElementById("telegram-actions");
  const errorEl = document.getElementById("telegram-error");
  errorEl.textContent = "";

  let user, status;
  try {
    [user, status] = await Promise.all([
      apiFetch("/api/auth/me"),
      apiFetch("/api/telegram/status").catch(() => null),
    ]);
  } catch {
    setTelegramStatus("Ошибка", "bg-slate-800 text-slate-400");
    return;
  }

  if (!status?.configured) {
    setTelegramStatus("Не настроен", "bg-amber-500/20 text-amber-400");
    actions.classList.add("hidden");
    errorEl.textContent = "Добавьте TELEGRAM_BOT_TOKEN в .env на сервере.";
    return;
  }

  actions.classList.remove("hidden");
  const connected = user.telegram_connected;
  const telegramLink = document.getElementById("telegram-link");

  if (connected) {
    const bot = status.bot_username ? `@${status.bot_username}` : "Telegram";
    setTelegramStatus(`Подключено (${bot})`, "bg-emerald-500/20 text-emerald-400");
    telegramLink.textContent = "Открыть бота";
    telegramLink.href = `https://t.me/${status.bot_username}`;
    document.getElementById("btn-telegram-disconnect").classList.remove("hidden");
  } else {
    setTelegramStatus("Не подключено", "bg-slate-800 text-slate-400");
    telegramLink.textContent = "Подключить Telegram";
    document.getElementById("btn-telegram-disconnect").classList.add("hidden");
    try {
      const res = await apiFetch("/api/telegram/link", { method: "POST" });
      telegramLink.href = res.link;
    } catch (err) {
      telegramLink.href = "#";
      errorEl.textContent = err.message;
    }
  }

  document.getElementById("btn-telegram-disconnect").onclick = async () => {
    await apiFetch("/api/telegram/disconnect", { method: "DELETE" });
    updateTelegramUI();
  };
}

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
  document.getElementById("welcome").textContent = "Не удалось загрузить dashboard";
  document.getElementById("total-value").textContent = "—";
  document.getElementById("total-cost").textContent = "—";
  document.getElementById("total-pnl").textContent = "—";
  document.getElementById("holdings-count").textContent = "—";
  document.getElementById("top-holdings").innerHTML = `
    <p class="text-red-400 text-sm">${err.message}</p>
  `;
});
updateTelegramUI();

document.getElementById("btn-portfolio-ai").onclick = async () => {
  const el = document.getElementById("portfolio-ai-result");
  el.classList.remove("hidden");
  el.innerHTML = `<p class="text-slate-400">AI анализирует портфель...</p>`;
  try {
    const data = await apiFetch("/api/portfolio/ai-analysis", { method: "POST", timeoutMs: 90000 });
    el.innerHTML = `
      <div class="flex items-center gap-2 mb-3">
        <h2 class="font-semibold text-lg">AI-анализ портфеля</h2>
        <span class="text-xs px-2 py-0.5 rounded-full ${data.ai_powered ? "bg-emerald-500/20 text-emerald-400" : "bg-slate-700 text-slate-300"}">${data.ai_powered ? "GPT" : "Базовый"}</span>
        <span class="text-amber-400 ml-auto">Рейтинг ${data.rating}/10</span>
      </div>
      <p class="text-slate-300 mb-4">${data.summary}</p>
      <p class="text-emerald-400 font-medium mb-4">${data.recommendation}</p>
      <div class="grid md:grid-cols-3 gap-4 text-sm">
        <div><h3 class="text-emerald-400 mb-1">Сильные</h3><ul>${data.strengths.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
        <div><h3 class="text-amber-400 mb-1">Слабые</h3><ul>${data.weaknesses.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
        <div><h3 class="text-red-400 mb-1">Риски</h3><ul>${data.risks.map(s=>`<li>• ${s}</li>`).join("")}</ul></div>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `<p class="text-red-400">${err.message}</p>`;
  }
};
