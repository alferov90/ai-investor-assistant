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
const orderConnection = document.getElementById("order-connection");
const orderForm = document.getElementById("order-form");
const orderPreviewEl = document.getElementById("order-preview");
const orderErrorEl = document.getElementById("order-error");
const orderStatusEl = document.getElementById("order-status");
const ordersEl = document.getElementById("broker-orders");

let previewState = null;
let connectionsState = [];
let orderPreviewState = null;

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

function showOrderError(message) {
  orderErrorEl.textContent = message || "";
}

function setOrderStatus(message) {
  orderStatusEl.textContent = message || "";
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

function directionLabel(direction) {
  return direction === "buy" ? "Покупка" : "Продажа";
}

function statusLabel(status) {
  const labels = {
    EXECUTION_REPORT_STATUS_FILL: "Исполнена",
    EXECUTION_REPORT_STATUS_REJECTED: "Отклонена",
    EXECUTION_REPORT_STATUS_CANCELLED: "Отменена",
    EXECUTION_REPORT_STATUS_NEW: "Ждёт исполнения",
    EXECUTION_REPORT_STATUS_PARTIALLYFILL: "Частично исполнена",
  };
  return labels[status] || status || "—";
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

function refreshOrderConnectionOptions() {
  if (!connectionsState.length) {
    orderConnection.innerHTML = `<option value="">Нет подключенных счетов</option>`;
    orderConnection.disabled = true;
    return;
  }
  orderConnection.disabled = false;
  orderConnection.innerHTML = connectionsState
    .map((connection) => {
      const mode = connection.sandbox ? "Sandbox" : "Real";
      return `<option value="${connection.id}">${escapeHtml(connection.account_name || connection.account_id)} · ${escapeHtml(mode)} · ${escapeHtml(connection.access_level)}</option>`;
    })
    .join("");
}

function renderOrderPreview(preview) {
  orderPreviewEl.classList.remove("hidden");
  const warnings = (preview.warnings || [])
    .map((warning) => `<li>${escapeHtml(warning)}</li>`)
    .join("");
  orderPreviewEl.innerHTML = `
    <div>
      <p class="daily-label">Инструмент</p>
      <p class="daily-value">${escapeHtml(preview.instrument.ticker)} · ${escapeHtml(preview.instrument.name)}</p>
      <p class="daily-sub">Лотность: ${preview.instrument.lot} · ${escapeHtml(preview.instrument.exchange || "биржа не указана")}</p>
    </div>
    <div>
      <p class="daily-label">Заявка</p>
      <p class="daily-value">${directionLabel(preview.direction)} · ${preview.lots} лот.</p>
      <p class="daily-sub">${formatMoney(preview.limit_price, preview.currency)} · примерно ${formatMoney(preview.estimated_amount, preview.currency)}</p>
    </div>
    <div class="broker-confirm-box">
      <p class="text-sm font-semibold">Для отправки введите:</p>
      <code>${escapeHtml(preview.confirm_text)}</code>
      <input id="order-confirm-text" class="input-field mt-3" placeholder="${escapeHtml(preview.confirm_text)}">
      <button id="btn-place-order" class="btn btn-primary mt-3">Отправить лимитную заявку</button>
    </div>
    <ul class="broker-warnings">${warnings}</ul>
  `;

  document.getElementById("btn-place-order").addEventListener("click", placeOrder);
}

function orderPayload() {
  return {
    connection_id: Number(orderConnection.value),
    ticker: document.getElementById("order-ticker").value.trim().toUpperCase(),
    direction: document.getElementById("order-direction").value,
    lots: Number(document.getElementById("order-lots").value),
    limit_price: Number(document.getElementById("order-price").value),
  };
}

orderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showOrderError("");
  setOrderStatus("Проверяю инструмент и параметры заявки...");
  orderPreviewEl.classList.add("hidden");
  orderPreviewState = null;

  try {
    orderPreviewState = await apiFetch("/api/brokers/orders/preview", {
      method: "POST",
      timeoutMs: 60000,
      body: JSON.stringify(orderPayload()),
    });
    setOrderStatus("");
    renderOrderPreview(orderPreviewState);
  } catch (err) {
    setOrderStatus("");
    showOrderError(err.message);
  }
});

async function placeOrder() {
  if (!orderPreviewState) return;
  showOrderError("");
  setOrderStatus("Отправляю заявку в T-Invest...");

  try {
    const result = await apiFetch("/api/brokers/orders/place", {
      method: "POST",
      timeoutMs: 90000,
      body: JSON.stringify({
        ...orderPayload(),
        confirm_text: document.getElementById("order-confirm-text").value,
      }),
    });
    setOrderStatus(result.message);
    orderPreviewEl.classList.add("hidden");
    orderPreviewState = null;
    loadOrders();
  } catch (err) {
    setOrderStatus("");
    showOrderError(err.message);
  }
}

function renderOrder(order) {
  const mode = order.sandbox ? "Sandbox" : "Real";
  const canCancel = !["EXECUTION_REPORT_STATUS_CANCELLED", "EXECUTION_REPORT_STATUS_FILL", "EXECUTION_REPORT_STATUS_REJECTED"].includes(order.status);
  return `
    <div class="broker-connection">
      <div>
        <div class="flex items-center gap-2 flex-wrap">
          <p class="font-display font-semibold text-lg">${escapeHtml(order.ticker)} · ${directionLabel(order.direction)}</p>
          <span class="badge">${escapeHtml(statusLabel(order.status))}</span>
          <span class="badge">${escapeHtml(mode)}</span>
        </div>
        <p class="text-sm mt-1" style="color: var(--text-muted);">${order.lots_requested} лот. · ${formatMoney(Number(order.limit_price), order.currency)} · исполнено ${order.lots_executed}</p>
        <p class="text-sm mt-1" style="color: var(--text-muted);">${formatDate(order.created_at)} · ${escapeHtml(order.order_id)}</p>
        ${order.message ? `<p class="text-sm mt-1" style="color: var(--text-muted);">${escapeHtml(order.message)}</p>` : ""}
      </div>
      <div class="card-actions flex-wrap">
        ${canCancel ? `<button class="btn btn-secondary btn-sm text-negative" data-cancel-order="${order.id}">Отменить</button>` : ""}
      </div>
    </div>
  `;
}

async function loadOrders() {
  try {
    const orders = await apiFetch("/api/brokers/orders");
    if (!orders.length) {
      ordersEl.innerHTML = `<p class="text-sm" style="color: var(--text-muted);">Заявок пока нет.</p>`;
      return;
    }

    ordersEl.innerHTML = orders.map(renderOrder).join("");
    ordersEl.querySelectorAll("[data-cancel-order]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirm("Отправить отмену заявки в T-Invest?")) return;
        button.disabled = true;
        button.textContent = "Отменяю...";
        try {
          await apiFetch(`/api/brokers/orders/${button.dataset.cancelOrder}/cancel`, {
            method: "POST",
            timeoutMs: 60000,
          });
          loadOrders();
        } catch (err) {
          showOrderError(err.message);
          loadOrders();
        }
      });
    });
  } catch (err) {
    ordersEl.innerHTML = `<p class="text-negative text-sm">${escapeHtml(err.message)}</p>`;
  }
}

async function loadConnections() {
  try {
    const connections = await apiFetch("/api/brokers/connections");
    connectionsState = connections;
    refreshOrderConnectionOptions();
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
document.getElementById("btn-refresh-orders").addEventListener("click", loadOrders);

loadConnections();
loadOrders();
