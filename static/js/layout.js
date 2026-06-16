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
    ["Сделки", "/transactions"],
    ["Дивиденды", "/dividends"],
    ["Watchlist", "/watchlist"],
    ["Анализ", "/analysis"],
    ["История", "/history"],
    ["Алерты", "/alerts"],
  ];
  const el = document.getElementById("main-nav");
  if (!el) return;
  el.innerHTML =
    links
      .map(
        ([label, href]) =>
          `<a href="${href}" class="nav-link${href === active ? " nav-link-active" : ""}">${label}</a>`
      )
      .join("") +
    `<button type="button" onclick="logout()" class="nav-logout">Выйти</button>`;
}

function injectLogo(targetId, href = "/dashboard") {
  const el = document.getElementById(targetId);
  if (el) el.innerHTML = logoHtml(href);
}

const HEAD_ASSETS = `
  <link rel="stylesheet" href="/static/css/theme.css">
  <script src="https://cdn.tailwindcss.com"><\/script>
`;
