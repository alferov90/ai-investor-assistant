if (!requireAuth()) throw new Error("redirecting");
renderNav("/broker");

const form = document.getElementById("broker-form");
const tokenInput = document.getElementById("tinvest-token");
const sandboxInput = document.getElementById("tinvest-sandbox");
const picker = document.getElementById("account-picker");
const accountSelect = document.getElementById("tinvest-account");
const errorEl = document.getElementById("broker-error");
const statusEl = document.getElementById("broker-status");
const listEl = document.getElementById("broker-connections");

let previewState = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showError(message) {
  errorEl.textContent = message || "";
}

function setStatus(message) {
  statusEl.textContent = message || "";
}

function formatDate(value) {
  if (!value) return "ещё не было";
  return new Date(value).toLocaleString("ru-RU");
}

function accessBadge(accessLevel) {
  const value = String(accessLevel || "").toLowerCase();
  if (value.includes("read")) return `<span class="badge badge-live">read-only</span>`;
  if (value.includes("full")) return `<span class="badge risk-high">full-access</span>`;
  return `<span class="badge">${escapeHtml(accessLevel || "доступ")}</span>`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  setStatus("Проверяю токен...");
  picker.classList.add("hidden");

  try {
    previewState = await apiFetch("/api/brokers/tinvest/preview", {
      method: "POST",
      timeoutMs: 60000,
      body: JSON.stringify({
        token: tokenInput.value.trim(),
        sandbox: sandboxInput.checked,
      }),
    });

    if (!previewState.accounts.length) {
      setStatus("");
      showError("T-Invest не вернул доступных счетов по этому токену.");
      return;
    }

    accountSelect.innerHTML = previewState.accounts
      .map(
        (account) =>
          `<option value="${escapeHtml(account.id)}">${escapeHtml(account.name)} · ${escapeHtml(account.type)} · ${escapeHtml(account.access_level)}</option>`
      )
      .join("");
    picker.classList.remove("hidden");
    setStatus(`Найдено счетов: ${previewState.accounts.length}. Выберите нужный и сохраните подключение.`);
  } catch (err) {
    setStatus("");
    showError(err.message);
  }
});

document.getElementById("btn-save-connection").addEventListener("click", async () => {
  if (!previewState) return;
  showError("");
  setStatus("Сохраняю подключение...");

  try {
    await apiFetch("/api/brokers/tinvest/connect", {
      method: "POST",
      timeoutMs: 60000,
      body: JSON.stringify({
        token: tokenInput.value.trim(),
        sandbox: sandboxInput.checked,
        account_id: accountSelect.value,
      }),
    });
    tokenInput.value = "";
    picker.classList.add("hidden");
    previewState = null;
    setStatus("Подключение сохранено. Теперь можно синхронизировать портфель.");
    loadConnections();
  } catch (err) {
    setStatus("");
    showError(err.message);
  }
});

function renderConnection(connection) {
  const mode = connection.sandbox ? "Sandbox" : "Реальный контур";
  const error = connection.last_error
    ? `<p class="text-negative text-sm mt-2">${escapeHtml(connection.last_error)}</p>`
    : "";
  return `
    <div class="broker-connection">
      <div>
        <div class="flex items-center gap-2 flex-wrap">
          <p class="font-display font-semibold text-lg">${escapeHtml(connection.account_name || connection.account_id)}</p>
          ${accessBadge(connection.access_level)}
          <span class="badge">${escapeHtml(mode)}</span>
        </div>
        <p class="text-sm mt-1" style="color: var(--text-muted);">${escapeHtml(connection.account_type)} · ${escapeHtml(connection.account_id)} · ${escapeHtml(connection.token_mask)}</p>
        <p class="text-sm mt-1" style="color: var(--text-muted);">Последняя синхронизация: ${formatDate(connection.last_synced_at)}</p>
        ${error}
      </div>
      <div class="card-actions flex-wrap">
        <button class="btn btn-primary btn-sm" data-sync="${connection.id}">Синхронизировать</button>
        <button class="btn btn-secondary btn-sm text-negative" data-delete="${connection.id}">Удалить</button>
      </div>
    </div>
  `;
}

async function loadConnections() {
  try {
    const connections = await apiFetch("/api/brokers/connections");
    if (!connections.length) {
      listEl.innerHTML = `<p class="text-sm" style="color: var(--text-muted);">Пока нет подключенных счетов.</p>`;
      return;
    }

    listEl.innerHTML = connections.map(renderConnection).join("");

    listEl.querySelectorAll("[data-sync]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Синхронизирую...";
        showError("");
        setStatus("");
        try {
          const result = await apiFetch(`/api/brokers/connections/${button.dataset.sync}/sync`, {
            method: "POST",
            timeoutMs: 90000,
          });
          setStatus(result.message);
          loadConnections();
        } catch (err) {
          showError(err.message);
          loadConnections();
        }
      });
    });

    listEl.querySelectorAll("[data-delete]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirm("Удалить брокерское подключение? Позиции портфеля останутся на месте.")) return;
        await apiFetch(`/api/brokers/connections/${button.dataset.delete}`, { method: "DELETE" });
        loadConnections();
      });
    });
  } catch (err) {
    listEl.innerHTML = `<p class="text-negative text-sm">${escapeHtml(err.message)}</p>`;
  }
}

document.getElementById("btn-refresh-connections").addEventListener("click", loadConnections);

loadConnections();
