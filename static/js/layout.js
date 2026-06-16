function logoHtml(href = "/") {
  return `<a href="${href}" class="logo">
    <span class="logo-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
        <path d="M4 18 L8 12 L12 15 L16 8 L20 11"/>
      </svg>
    </span>
    <span><span class="logo-accent">AI</span> Investor</span>
  </a>`;
}

function renderNav(active) {
  const links = [
    ["Dashboard", "/dashboard"],
    ["Портфель", "/portfolio"],
    ["Брокер", "/broker"],
    ["Сделки", "/transactions"],
    ["Дивиденды", "/dividends"],
    ["Watchlist", "/watchlist"],
    ["Анализ", "/analysis"],
    ["История", "/history"],
    ["Алерты", "/alerts"],
  ];
  const el = document.getElementById("main-nav");
  if (!el) return;
  el.className = "nav-root";
  const navLinks = links
    .map(
      ([label, href]) =>
        `<a href="${href}" class="nav-link${href === active ? " nav-link-active" : ""}">${label}</a>`
    )
    .join("");
  el.innerHTML =
    `<div class="nav-desktop" aria-label="Главное меню">
      ${navLinks}
      <button type="button" class="nav-logout" data-nav-logout>Выйти</button>
    </div>
    <button type="button" class="nav-menu-button" aria-label="Открыть меню" aria-expanded="false" aria-controls="mobile-nav-panel">
      <span></span><span></span><span></span>
    </button>
    <div class="nav-backdrop" data-nav-close></div>
    <aside class="nav-drawer" id="mobile-nav-panel" aria-label="Главное меню">
      <div class="nav-drawer-header">
        <span class="nav-drawer-title">Меню</span>
        <button type="button" class="nav-drawer-close" aria-label="Закрыть меню" data-nav-close>×</button>
      </div>
      <div class="nav-drawer-links">${navLinks}</div>
      <button type="button" class="nav-drawer-logout" data-nav-logout>Выйти</button>
    </aside>`;

  const toggle = el.querySelector(".nav-menu-button");
  const closeTargets = el.querySelectorAll("[data-nav-close]");
  const logoutTargets = el.querySelectorAll("[data-nav-logout]");

  const setOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  };

  toggle.addEventListener("click", () => setOpen(!document.body.classList.contains("nav-open")));
  closeTargets.forEach((target) => target.addEventListener("click", () => setOpen(false)));
  el.querySelectorAll(".nav-drawer .nav-link").forEach((link) => {
    link.addEventListener("click", () => setOpen(false));
  });
  logoutTargets.forEach((button) => {
    button.addEventListener("click", () => {
      setOpen(false);
      logout();
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });
}

function injectLogo(targetId, href = "/dashboard") {
  const el = document.getElementById(targetId);
  if (el) el.innerHTML = logoHtml(href);
}

const HEAD_ASSETS = `
  <link rel="stylesheet" href="/static/css/theme.css">
  <script src="https://cdn.tailwindcss.com"><\/script>
`;
