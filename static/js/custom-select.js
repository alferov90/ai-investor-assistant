/**
 * Custom dropdown — полностью стилизуемая замена native <select>.
 * Usage: initCustomSelect("condition", [{ value: "above", label: "Цена выше" }, ...]);
 */
function initCustomSelect(id, options, defaultValue) {
  const hidden = document.getElementById(id);
  if (!hidden || hidden.dataset.customSelect === "1") return;

  const wrap = document.createElement("div");
  wrap.className = "custom-select";
  wrap.id = `${id}-custom`;

  hidden.type = "hidden";
  hidden.dataset.customSelect = "1";
  hidden.value = defaultValue || options[0]?.value || "";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "custom-select-trigger input-field";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const labelSpan = document.createElement("span");
  const chevron = document.createElement("span");
  chevron.className = "custom-select-chevron";
  chevron.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>`;
  trigger.append(labelSpan, chevron);

  const menu = document.createElement("ul");
  menu.className = "custom-select-menu";
  menu.setAttribute("role", "listbox");

  function currentLabel() {
    const opt = options.find((o) => o.value === hidden.value);
    return opt ? opt.label : "";
  }

  function setValue(value) {
    hidden.value = value;
    labelSpan.textContent = currentLabel();
    menu.querySelectorAll(".custom-select-option").forEach((el) => {
      const selected = el.dataset.value === value;
      el.classList.toggle("is-selected", selected);
      el.setAttribute("aria-selected", selected ? "true" : "false");
    });
  }

  options.forEach((opt) => {
    const li = document.createElement("li");
    li.className = "custom-select-option";
    li.dataset.value = opt.value;
    li.setAttribute("role", "option");
    li.innerHTML = `<span class="custom-select-check">✓</span><span>${opt.label}</span>`;
    li.onclick = (e) => {
      e.stopPropagation();
      setValue(opt.value);
      close();
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    };
    menu.appendChild(li);
  });

  function open() {
    document.querySelectorAll(".custom-select.open").forEach((el) => {
      if (el !== wrap) el.classList.remove("open");
    });
    wrap.classList.add("open");
    trigger.setAttribute("aria-expanded", "true");
  }

  function close() {
    wrap.classList.remove("open");
    trigger.setAttribute("aria-expanded", "false");
  }

  function toggle() {
    wrap.classList.contains("open") ? close() : open();
  }

  trigger.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggle();
  };

  hidden.parentNode.insertBefore(wrap, hidden);
  wrap.append(hidden, trigger, menu);
  setValue(hidden.value);

  if (!window._customSelectDocListener) {
    window._customSelectDocListener = true;
    document.addEventListener("click", () => {
      document.querySelectorAll(".custom-select.open").forEach((el) => el.classList.remove("open"));
      document.querySelectorAll(".custom-select-trigger[aria-expanded='true']").forEach((el) => {
        el.setAttribute("aria-expanded", "false");
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document.querySelectorAll(".custom-select.open").forEach((el) => el.classList.remove("open"));
      }
    });
  }

  return { setValue, getValue: () => hidden.value };
}
