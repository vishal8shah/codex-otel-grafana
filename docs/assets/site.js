const pricing = {
  "gpt-5.5 standard": { input: 5, cached: 0.5, output: 30 },
  "gpt-5.4 standard": { input: 2.5, cached: 0.25, output: 15 },
  "gpt-5.4-mini standard": { input: 0.75, cached: 0.075, output: 4.5 },
  "gpt-5.3-codex standard": { input: 1.75, cached: 0.175, output: 14 },
  "local model": { input: 0, cached: 0, output: 0 }
};

const formatMoney = (value) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value < 10 ? 4 : 2
  }).format(value);

function numberValue(id) {
  const value = Number(document.getElementById(id)?.value || 0);
  return Number.isFinite(value) ? value : 0;
}

function calculateCost() {
  const model = document.getElementById("model")?.value || "gpt-5.5 standard";
  const rates = pricing[model] || pricing["gpt-5.5 standard"];
  const runs = numberValue("runs");
  const input = numberValue("inputTokens");
  const cached = Math.min(numberValue("cachedTokens"), input);
  const output = numberValue("outputTokens");
  const regularInput = Math.max(input - cached, 0);
  const perRun = ((regularInput * rates.input) + (cached * rates.cached) + (output * rates.output)) / 1_000_000;
  const daily = perRun * runs;
  const monthly = daily * 30;
  const cacheSavings = ((cached * rates.input) - (cached * rates.cached)) / 1_000_000 * runs;
  const tokensPerDay = (input + output) * runs;

  const values = {
    perRunCost: formatMoney(perRun),
    dailyCost: formatMoney(daily),
    monthlyCost: formatMoney(monthly),
    cacheSavings: formatMoney(Math.max(cacheSavings, 0)),
    tokensPerDay: new Intl.NumberFormat("en-US").format(tokensPerDay)
  };

  Object.entries(values).forEach(([id, value]) => {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  });
}

function setupTheme() {
  const stored = localStorage.getItem("theme");
  const initial = stored || "dark";
  document.documentElement.dataset.theme = initial;

  const button = document.getElementById("themeToggle");
  const label = document.getElementById("themeLabel");
  const sync = () => {
    const isLight = document.documentElement.dataset.theme === "light";
    if (button) button.setAttribute("aria-label", isLight ? "Switch to dark mode" : "Switch to light mode");
    if (label) label.textContent = isLight ? "Light" : "Dark";
    if (button) button.textContent = isLight ? "☀" : "☾";
  };

  if (button) {
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      localStorage.setItem("theme", next);
      sync();
    });
  }

  sync();
}

function setupSearch() {
  const input = document.getElementById("docSearch");
  if (!input) return;
  input.addEventListener("input", () => {
    const term = input.value.trim().toLowerCase();
    document.querySelectorAll("[data-search]").forEach((node) => {
      const hit = node.textContent.toLowerCase().includes(term);
      node.style.display = !term || hit ? "" : "none";
    });
  });
}

function setupNavState() {
  const currentPath = location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll(".nav-link,.nav-sub").forEach((link) => {
    const href = link.getAttribute("href") || "";
    if (href === currentPath || (currentPath === "" && href === "index.html")) {
      link.classList.add("active");
    }
  });

  const anchorLinks = Array.from(document.querySelectorAll(".nav-link[href^='#'],.nav-sub[href^='#']"));
  const sections = anchorLinks
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  const update = () => {
    let current = sections[0]?.id;
    sections.forEach((section) => {
      if (section.getBoundingClientRect().top < 170) current = section.id;
    });
    anchorLinks.forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href") === `#${current}`);
    });
  };

  document.addEventListener("scroll", update, { passive: true });
  update();
}

function setupTabs() {
  const tabs = document.querySelectorAll("[data-tab]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((node) => node.classList.remove("active"));
      tab.classList.add("active");
      const language = tab.dataset.tab;
      document.querySelectorAll("[data-code]").forEach((panel) => {
        panel.hidden = panel.dataset.code !== language;
      });
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#model,#runs,#inputTokens,#cachedTokens,#outputTokens")
    .forEach((element) => element.addEventListener("input", calculateCost));
  setupTheme();
  setupSearch();
  setupNavState();
  setupTabs();
  calculateCost();
});
