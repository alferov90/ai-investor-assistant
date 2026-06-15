function renderNav(active) {
  const links = [
    ["Dashboard", "/dashboard"],
    ["Портфель", "/portfolio"],
    ["Watchlist", "/watchlist"],
    ["Анализ", "/analysis"],
    ["История", "/history"],
    ["Алерты", "/alerts"],
  ];
  const el = document.getElementById("main-nav");
  if (!el) return;
  el.innerHTML = links
    .map(
      ([label, href]) =>
        `<a href="${href}" class="${href === active ? "text-emerald-400" : "text-slate-300 hover:text-white"}">${label}</a>`
    )
    .join("") + `<button onclick="logout()" class="text-slate-400 hover:text-white ml-2">Выйти</button>`;
}
